"""
Swarm Parallel Model Caller
============================
Call multiple models in parallel, rank responses by quality,
and return the best results.
"""

import asyncio
import json
import time
import urllib.request
import urllib.error
from typing import Optional

from swarm_router.config import SwarmConfig, ModelEntry, default_config


# ---------------------------------------------------------------------------
# HTTP helper (stdlib only — zero extra deps for async path)
# ---------------------------------------------------------------------------


def _http_post(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Single model call (async)
# ---------------------------------------------------------------------------


async def call_model(
    entry: ModelEntry,
    prompt: str,
    timeout: int = 60,
) -> dict:
    """Call a single model asynchronously and return structured result."""
    url = f"{entry.endpoint.url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {entry.endpoint.api_key}",
    }
    payload = {
        "model": entry.model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }

    start = time.monotonic()
    try:
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, _http_post, url, headers, payload, timeout),
            timeout=timeout,
        )
        elapsed = time.monotonic() - start
        content = response["choices"][0]["message"]["content"]
        return {
            "model": entry.model_id,
            "status": "ok",
            "elapsed_s": round(elapsed, 2),
            "content": content,
            "tokens": response.get("usage", {}).get("total_tokens"),
        }
    except asyncio.TimeoutError:
        return {
            "model": entry.model_id,
            "status": "timeout",
            "elapsed_s": round(time.monotonic() - start, 2),
            "content": None,
            "tokens": None,
        }
    except Exception as exc:
        return {
            "model": entry.model_id,
            "status": "error",
            "elapsed_s": round(time.monotonic() - start, 2),
            "content": None,
            "error": str(exc),
            "tokens": None,
        }


# ---------------------------------------------------------------------------
# Quality ranking
# ---------------------------------------------------------------------------


def _score_result(result: dict) -> float:
    """Heuristic quality score for a completed result."""
    if result["status"] != "ok" or not result.get("content"):
        return -1.0

    content = result["content"]
    length_score = min(len(content) / 500.0, 3.0)
    if len(content) < 50:
        length_score = 0.1

    structure_score = 0.0
    if "```" in content:
        structure_score += 0.5
    if any(line.startswith("#") for line in content.splitlines()):
        structure_score += 0.3

    speed_score = max(0.0, 1.0 - result["elapsed_s"] / 30.0)
    return length_score + structure_score + speed_score


def rank_results(results: list[dict]) -> list[dict]:
    """Return results sorted by quality score descending."""
    return sorted(results, key=_score_result, reverse=True)


# ---------------------------------------------------------------------------
# Swarm call
# ---------------------------------------------------------------------------


async def swarm_call(
    prompt: str,
    tier: str = "fast",
    max_models: int = 3,
    timeout: int = 60,
    config: Optional[SwarmConfig] = None,
) -> list[dict]:
    """
    Call up to max_models from the chosen tier in parallel.
    Returns ranked results (best first).
    """
    cfg = config or default_config()
    candidates = cfg.get_tier_models(tier)
    selected = candidates[:max_models]

    tasks = [call_model(m, prompt, timeout) for m in selected]
    results = await asyncio.gather(*tasks)
    return rank_results(list(results))


async def swarm_first(
    prompt: str,
    tier: str = "fast",
    max_models: int = 3,
    timeout: int = 60,
    config: Optional[SwarmConfig] = None,
) -> dict:
    """Return the first model to respond successfully (race mode)."""
    cfg = config or default_config()
    candidates = cfg.get_tier_models(tier)
    selected = candidates[:max_models]

    tasks = {asyncio.create_task(call_model(m, prompt, timeout)): m for m in selected}
    pending = set(tasks.keys())

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            result = task.result()
            if result["status"] == "ok":
                for t in pending:
                    t.cancel()
                return result

    return {"model": None, "status": "all_failed", "content": None}
