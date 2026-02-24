"""
SwarmRouter Orchestrator
========================
Core orchestration logic: auto-routing, multi-model consensus, and
knowledge-enriched pipelines.

Designed to work with any OpenAI-compatible endpoint (LiteLLM, vLLM,
OpenRouter, Ollama, etc.)
"""

import json
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from swarm_router.config import SwarmConfig, default_config
from swarm_router.health import ServiceHealth

log = logging.getLogger("swarm-router")

# ---------------------------------------------------------------------------
# HTTP session with retry
# ---------------------------------------------------------------------------


def _make_session(retries: int = 2, backoff: float = 0.5) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


_SESSION = _make_session()

# ---------------------------------------------------------------------------
# LLM Caller
# ---------------------------------------------------------------------------


def _chat_completion(
    model: str,
    messages: list[dict],
    base_url: str,
    api_key: str,
    timeout: tuple[float, float],
) -> dict:
    """POST to /v1/chat/completions. Raises on failure."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    r = _SESSION.post(url, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _extract_text(response: dict) -> str:
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return str(response)


# ---------------------------------------------------------------------------
# Auto-Router
# ---------------------------------------------------------------------------


def auto_route(
    prompt: str,
    system: Optional[str] = None,
    tier: Optional[str] = None,
    config: Optional[SwarmConfig] = None,
    health: Optional[ServiceHealth] = None,
) -> dict:
    """
    Route a prompt to the best available model for its complexity tier.

    Falls back through tiers if the primary tier is unavailable.
    Returns {'model': str, 'response': str, 'tier': str, 'latency_s': float}.
    """
    cfg = config or default_config()
    if health:
        health.refresh()

    detected_tier = tier or cfg.classify_complexity(prompt)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Map complexity tiers to search order
    tier_map = {
        "T1": ["fast"],
        "T2": ["power", "fast"],
        "T3": ["deep", "power", "fast"],
    }
    search_order = tier_map.get(detected_tier, ["fast"])

    last_error = None
    for t in search_order:
        candidates = cfg.get_tier_models(t)
        timeout = cfg.get_tier_timeout(t)
        for entry in candidates:
            # Skip if health monitor says endpoint is down
            if health and not health.is_up(entry.endpoint.name):
                log.debug(
                    "Skipping %s - %s is down", entry.model_id, entry.endpoint.name
                )
                continue
            try:
                t0 = time.monotonic()
                resp = _chat_completion(
                    entry.model_id,
                    messages,
                    entry.endpoint.url,
                    entry.endpoint.api_key,
                    timeout,
                )
                latency = time.monotonic() - t0
                text = _extract_text(resp)
                log.info(
                    "auto_route: model=%s tier=%s latency=%.1fs",
                    entry.model_id,
                    t,
                    latency,
                )
                return {
                    "model": entry.model_id,
                    "tier": t,
                    "response": text,
                    "latency_s": round(latency, 2),
                }
            except Exception as exc:
                log.warning("auto_route: model=%s failed: %s", entry.model_id, exc)
                last_error = exc

    raise RuntimeError(
        f"All models exhausted for tier {detected_tier}. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Multi-Model Consensus
# ---------------------------------------------------------------------------


def consensus(
    prompt: str,
    models: Optional[list] = None,
    system: Optional[str] = None,
    max_workers: int = 5,
    call_timeout: float = 90.0,
    config: Optional[SwarmConfig] = None,
    health: Optional[ServiceHealth] = None,
) -> dict:
    """
    Send prompt to multiple models in parallel and synthesize a merged answer.
    Returns {'merged': str, 'individual': list[dict], 'model_count': int}.
    """
    cfg = config or default_config()
    if health:
        health.refresh()

    if models is None:
        # Default: one from each tier
        models = []
        for t in ["fast", "power", "deep"]:
            tier_models = cfg.get_tier_models(t)
            if tier_models:
                models.append(tier_models[0])

    messages_base = []
    if system:
        messages_base.append({"role": "system", "content": system})
    messages_base.append({"role": "user", "content": prompt})

    results = []

    def _call(entry):
        if health and not health.is_up(entry.endpoint.name):
            return {
                "model": entry.model_id,
                "response": None,
                "error": f"{entry.endpoint.name} unavailable",
            }
        timeout = cfg.get_tier_timeout(entry.tier)
        try:
            t0 = time.monotonic()
            resp = _chat_completion(
                entry.model_id,
                list(messages_base),
                entry.endpoint.url,
                entry.endpoint.api_key,
                timeout,
            )
            latency = time.monotonic() - t0
            return {
                "model": entry.model_id,
                "response": _extract_text(resp),
                "latency_s": round(latency, 2),
                "error": None,
            }
        except Exception as exc:
            return {"model": entry.model_id, "response": None, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(_call, m): m for m in models}
        for fut in as_completed(futs, timeout=call_timeout + 10):
            try:
                results.append(fut.result())
            except Exception as exc:
                results.append(
                    {"model": "unknown", "response": None, "error": str(exc)}
                )

    successful = [r for r in results if r.get("response")]
    if not successful:
        raise RuntimeError("All consensus models failed.")

    # Synthesize
    synthesis_prompt = (
        "You are a synthesis agent. Multiple AI models answered the same question.\n"
        "Combine their insights into a single, comprehensive, non-redundant answer.\n\n"
        f"ORIGINAL QUESTION:\n{prompt}\n\nMODEL RESPONSES:\n"
    )
    for i, r in enumerate(successful, 1):
        synthesis_prompt += f"\n--- Model {i}: {r['model']} ---\n{r['response']}\n"
    synthesis_prompt += "\nSYNTHESIZED ANSWER:"

    try:
        merged_result = auto_route(
            synthesis_prompt, tier="T2", config=cfg, health=health
        )
        merged = merged_result["response"]
    except Exception:
        merged = "\n\n---\n\n".join(
            f"[{r['model']}]\n{r['response']}" for r in successful
        )

    return {"merged": merged, "individual": results, "model_count": len(successful)}


# ---------------------------------------------------------------------------
# Knowledge-Enriched Pipeline
# ---------------------------------------------------------------------------


def _knowledge_search(knowledge_url: str, query: str) -> list[dict]:
    """Search a knowledge graph API (Cognee-compatible)."""
    try:
        url = f"{knowledge_url.rstrip('/')}/search"
        r = _SESSION.post(
            url,
            json={"query": query, "query_type": "GRAPH_COMPLETION"},
            timeout=(5, 30),
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("results", [data])
    except Exception as exc:
        log.warning("knowledge_search failed: %s", exc)
        return []


def _knowledge_add(
    knowledge_url: str, text: str, dataset: str = "orchestrator"
) -> bool:
    """Add text to knowledge graph."""
    try:
        url = f"{knowledge_url.rstrip('/')}/add"
        r = _SESSION.post(
            url, json={"text": text, "dataset_name": dataset}, timeout=(5, 60)
        )
        r.raise_for_status()
        return True
    except Exception as exc:
        log.warning("knowledge_add failed: %s", exc)
        return False


def _format_context(results: list[dict]) -> str:
    if not results:
        return ""
    lines = ["RELEVANT KNOWLEDGE FROM MEMORY:"]
    for i, item in enumerate(results[:5], 1):
        if isinstance(item, dict):
            text = (
                item.get("text")
                or item.get("content")
                or item.get("summary")
                or json.dumps(item)
            )
        else:
            text = str(item)
        lines.append(f"[{i}] {text[:500]}")
    return "\n".join(lines)


def pipeline(
    prompt: str,
    enrich: bool = True,
    store: bool = True,
    use_consensus: bool = False,
    tier: Optional[str] = None,
    config: Optional[SwarmConfig] = None,
    health: Optional[ServiceHealth] = None,
) -> dict:
    """
    Full knowledge-enriched pipeline:
      1. Search knowledge graph for context (if enrich=True)
      2. Enrich prompt with retrieved context
      3. Run query (auto-route or consensus)
      4. Store result back (if store=True)

    Returns full result dict including context used.
    """
    cfg = config or default_config()
    if health:
        health.refresh()

    # Step 1: Retrieve context
    context_results = []
    enriched_prompt = prompt
    if enrich and cfg.knowledge_url:
        log.info("pipeline: searching knowledge graph for context...")
        context_results = _knowledge_search(cfg.knowledge_url, prompt)
        context_str = _format_context(context_results)
        if context_str:
            enriched_prompt = f"{context_str}\n\nUSER QUESTION:\n{prompt}"
            log.info("pipeline: enriched with %d results", len(context_results))

    # Step 2: Generate answer
    t0 = time.monotonic()
    if use_consensus:
        result = consensus(enriched_prompt, config=cfg, health=health)
        answer = result["merged"]
        model_info = {"consensus": True, "model_count": result["model_count"]}
    else:
        result = auto_route(enriched_prompt, tier=tier, config=cfg, health=health)
        answer = result["response"]
        model_info = {"model": result["model"], "tier": result["tier"]}
    total_latency = time.monotonic() - t0

    # Step 3: Store result (fire-and-forget)
    if store and cfg.knowledge_url:
        memory_text = (
            f"Q: {prompt}\n\nA: {answer}\n\n"
            f"Generated by: {json.dumps(model_info)} at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
        )
        threading.Thread(
            target=_knowledge_add,
            args=(cfg.knowledge_url, memory_text),
            daemon=True,
        ).start()

    return {
        "answer": answer,
        "prompt_original": prompt,
        "prompt_enriched": enriched_prompt if enrich else prompt,
        "context_results_count": len(context_results),
        "model_info": model_info,
        "total_latency_s": round(total_latency, 2),
        "stored": store,
    }
