"""
SwarmRouter CLI
===============
Command-line interface for the AI orchestration pipeline.

Usage:
    swarm-router query "What is quantum computing?"
    swarm-router consensus "Compare React vs Vue"
    swarm-router pipeline "Research AI agent patterns" --enrich --store
    swarm-router health
    swarm-router serve --port 9000
"""

import argparse
import json
import logging
import sys

from swarm_router.config import SwarmConfig, default_config
from swarm_router.health import ServiceHealth
from swarm_router.orchestrator import auto_route, consensus, pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _build_health(config: SwarmConfig) -> ServiceHealth:
    h = ServiceHealth()
    h.register(
        "primary",
        f"{config.primary.url}/health/liveliness",
        {"Authorization": f"Bearer {config.primary.api_key}"},
    )
    if config.secondary:
        h.register(
            "secondary",
            f"{config.secondary.url}/health/liveliness",
            {"Authorization": f"Bearer {config.secondary.api_key}"},
        )
    if config.knowledge_url:
        base = config.knowledge_url.replace("/api/v1", "").rstrip("/")
        h.register("knowledge", f"{base}/")
    return h


def cmd_health(args, config: SwarmConfig) -> int:
    print("\n--- Service Health Check ---")
    h = _build_health(config)
    status = h.refresh()
    all_ok = True
    for name, up in status.items():
        icon = "UP  " if up else "DOWN"
        color = "\033[32m" if up else "\033[31m"
        reset = "\033[0m"
        print(f"  {color}{icon}{reset}  {name}")
        if not up:
            all_ok = False
    print()
    return 0 if all_ok else 1


def cmd_query(args, config: SwarmConfig) -> int:
    h = _build_health(config)
    try:
        result = auto_route(
            args.prompt, tier=getattr(args, "tier", None), config=config, health=h
        )
        print(
            f"\n[Model: {result['model']} | Tier: {result['tier']} | {result['latency_s']}s]\n"
        )
        print(result["response"])
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_consensus(args, config: SwarmConfig) -> int:
    h = _build_health(config)
    try:
        result = consensus(args.prompt, config=config, health=h)
        print(f"\n[Consensus from {result['model_count']} models]\n")
        print(result["merged"])
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_pipeline(args, config: SwarmConfig) -> int:
    h = _build_health(config)
    try:
        result = pipeline(
            args.prompt,
            enrich=getattr(args, "enrich", False),
            store=getattr(args, "store", False),
            use_consensus=getattr(args, "consensus", False),
            config=config,
            health=h,
        )
        print(
            f"\n[Pipeline | context={result['context_results_count']} | "
            f"latency={result['total_latency_s']}s | stored={result['stored']}]\n"
        )
        print(result["answer"])
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def cmd_serve(args, config: SwarmConfig) -> int:
    port = getattr(args, "port", 9000)
    h = _build_health(config)
    h.refresh()

    try:
        from flask import Flask, request as freq, jsonify
    except ImportError:
        print(
            "Flask not installed. Install with: pip install swarm-router[server]",
            file=sys.stderr,
        )
        return 1

    app = Flask("swarm-router")

    @app.route("/health", methods=["GET"])
    def health_ep():
        status = h.refresh()
        ok = all(status.values())
        return jsonify({"status": "ok" if ok else "degraded", "services": status}), 200

    @app.route("/v1/query", methods=["POST"])
    def query_ep():
        body = freq.get_json(force=True) or {}
        prompt = body.get("prompt", "")
        if not prompt:
            return jsonify({"error": "prompt required"}), 400
        try:
            result = auto_route(
                prompt,
                system=body.get("system"),
                tier=body.get("tier"),
                config=config,
                health=h,
            )
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/v1/consensus", methods=["POST"])
    def consensus_ep():
        body = freq.get_json(force=True) or {}
        prompt = body.get("prompt", "")
        if not prompt:
            return jsonify({"error": "prompt required"}), 400
        try:
            result = consensus(prompt, config=config, health=h)
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/v1/pipeline", methods=["POST"])
    def pipeline_ep():
        body = freq.get_json(force=True) or {}
        prompt = body.get("prompt", "")
        if not prompt:
            return jsonify({"error": "prompt required"}), 400
        try:
            result = pipeline(
                prompt,
                enrich=body.get("enrich", True),
                store=body.get("store", True),
                use_consensus=body.get("consensus", False),
                config=config,
                health=h,
            )
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    print(f"\nSwarmRouter API running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    return 0


def health():
    """Entrypoint for swarm-health command."""
    config = default_config()
    sys.exit(cmd_health(None, config))


def main():
    config = default_config()

    parser = argparse.ArgumentParser(
        description="SwarmRouter — Multi-model AI Orchestration Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("health", help="Check all service health")

    p_q = sub.add_parser("query", help="Single query with auto-routing")
    p_q.add_argument("prompt")
    p_q.add_argument("--tier", choices=["T1", "T2", "T3"])

    p_c = sub.add_parser("consensus", help="Multi-model consensus")
    p_c.add_argument("prompt")

    p_p = sub.add_parser("pipeline", help="Knowledge-enriched pipeline")
    p_p.add_argument("prompt")
    p_p.add_argument("--enrich", action="store_true")
    p_p.add_argument("--store", action="store_true")
    p_p.add_argument("--consensus", action="store_true")

    p_s = sub.add_parser("serve", help="Start HTTP API server")
    p_s.add_argument("--port", type=int, default=9000)

    args = parser.parse_args()
    dispatch = {
        "health": cmd_health,
        "query": cmd_query,
        "consensus": cmd_consensus,
        "pipeline": cmd_pipeline,
        "serve": cmd_serve,
    }

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handler = dispatch.get(args.command)
    sys.exit(handler(args, config))


if __name__ == "__main__":
    main()
