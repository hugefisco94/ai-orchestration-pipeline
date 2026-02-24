"""
MCP Bridge Server
=================
Exposes SwarmRouter capabilities as an MCP (Model Context Protocol) server.
Connect to any MCP-compatible client (Claude Code, OpenCode, etc.) via stdio.

Usage:
    python -m swarm_router.mcp_bridge
    python -m swarm_router.mcp_bridge --print-config
"""

import asyncio
import json
import sys
import time
import argparse
from typing import Optional

from swarm_router.config import SwarmConfig, default_config

# ---------------------------------------------------------------------------
# HTTP helpers (stdlib — no extra deps)
# ---------------------------------------------------------------------------

import urllib.request
import urllib.error


def _http_post(url: str, headers: dict, body: dict, timeout: int = 30) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(url: str, headers: dict, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _tool_query(arguments: dict, config: SwarmConfig) -> str:
    """Route a query through the best available model."""
    prompt = arguments.get("prompt", "")
    model = arguments.get("model")
    timeout = int(arguments.get("timeout", 30))

    if not prompt:
        return "Error: 'prompt' is required."

    endpoint = config.primary
    url = f"{endpoint.url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {endpoint.api_key}",
    }
    payload = {
        "model": model or (config.models[0].model_id if config.models else "default"),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }

    loop = asyncio.get_event_loop()
    try:
        response = await asyncio.wait_for(
            loop.run_in_executor(None, _http_post, url, headers, payload, timeout),
            timeout=timeout + 5,
        )
        content = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})
        return f"Tokens: {usage.get('total_tokens', 'n/a')}\n\n{content}"
    except asyncio.TimeoutError:
        return f"Error: timed out after {timeout}s."
    except Exception as exc:
        return f"Error: {exc}"


async def _tool_swarm(arguments: dict, config: SwarmConfig) -> str:
    """Call multiple models in parallel."""
    prompt = arguments.get("prompt", "")
    tier = arguments.get("tier", "fast")
    max_models = int(arguments.get("max_models", 3))

    if not prompt:
        return "Error: 'prompt' is required."

    from swarm_router.swarm import swarm_call

    results = await swarm_call(prompt, tier=tier, max_models=max_models, config=config)
    parts = [f"Swarm | tier={tier} | {len(results)} model(s)\n"]
    for i, r in enumerate(results, 1):
        parts.append(
            f"\n[{i}] {r['model']} | {r['status']} | {r.get('elapsed_s', '?')}s"
        )
        if r["status"] == "ok" and r.get("content"):
            parts.append(r["content"][:2000])
        elif r.get("error"):
            parts.append(f"Error: {r['error']}")
    return "\n".join(parts)


async def _tool_status(arguments: dict, config: SwarmConfig) -> str:
    """Check health of all endpoints."""
    loop = asyncio.get_event_loop()

    async def probe(name: str, url: str, headers: dict) -> str:
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, _http_get, url, headers, 5),
                timeout=7,
            )
            return f"  {name:<30} OK"
        except Exception as exc:
            return f"  {name:<30} FAIL  ({exc})"

    checks = [
        probe(
            "Primary",
            f"{config.primary.url}/health/liveliness",
            {"Authorization": f"Bearer {config.primary.api_key}"},
        ),
    ]
    if config.secondary:
        checks.append(
            probe(
                "Secondary",
                f"{config.secondary.url}/health/liveliness",
                {"Authorization": f"Bearer {config.secondary.api_key}"},
            )
        )
    if config.knowledge_url:
        base = config.knowledge_url.replace("/api/v1", "").rstrip("/")
        checks.append(probe("Knowledge Graph", f"{base}/", {}))

    results = await asyncio.gather(*checks)
    return "Service Status:\n" + "\n".join(results)


# ---------------------------------------------------------------------------
# MCP Tool Registry
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "swarm_query",
        "description": "Route a query through the best AI model (auto-selected by complexity).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The query or task"},
                "model": {
                    "type": "string",
                    "description": "Override model ID (optional)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout seconds (default: 30)",
                    "default": 30,
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "swarm_call",
        "description": "Call multiple AI models in parallel. Tiers: fast (3-10s), power (5-14s), deep (21s+).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The query or task"},
                "tier": {
                    "type": "string",
                    "enum": ["fast", "power", "deep"],
                    "default": "fast",
                },
                "max_models": {"type": "integer", "default": 3},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "swarm_status",
        "description": "Check health of all connected AI services.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

TOOL_HANDLERS = {
    "swarm_query": _tool_query,
    "swarm_call": _tool_swarm,
    "swarm_status": _tool_status,
}

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 / MCP dispatcher
# ---------------------------------------------------------------------------


async def handle_request(request: dict, config: SwarmConfig) -> Optional[dict]:
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "swarm-router-mcp", "version": "0.1.0"},
            },
        }

    if method.startswith("notifications/"):
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True,
                },
            }
        try:
            result_text = await handler(arguments, config)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


# ---------------------------------------------------------------------------
# Stdio server
# ---------------------------------------------------------------------------


async def run_server(config: Optional[SwarmConfig] = None):
    """Run MCP server on stdio."""
    cfg = config or default_config()
    print("swarm-router-mcp starting on stdio...", file=sys.stderr)

    import threading
    import queue

    input_queue: queue.Queue = queue.Queue()

    def _stdin_reader():
        try:
            for line in sys.stdin.buffer:
                input_queue.put(line)
        except Exception:
            pass
        finally:
            input_queue.put(None)

    threading.Thread(target=_stdin_reader, daemon=True).start()

    loop = asyncio.get_event_loop()
    buffer = b""
    while True:
        try:
            chunk = await loop.run_in_executor(None, input_queue.get)
            if chunk is None:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                response = await handle_request(request, cfg)
                if response is not None:
                    response_bytes = json.dumps(response).encode("utf-8") + b"\n"
                    sys.stdout.buffer.write(response_bytes)
                    sys.stdout.buffer.flush()
        except Exception as exc:
            print(f"Server error: {exc}", file=sys.stderr)
            break


def main():
    parser = argparse.ArgumentParser(description="SwarmRouter MCP Bridge")
    parser.add_argument(
        "--print-config", action="store_true", help="Print MCP config snippet"
    )
    args = parser.parse_args()

    if args.print_config:
        print(
            json.dumps(
                {
                    "mcpServers": {
                        "swarm-router": {
                            "command": "python",
                            "args": ["-m", "swarm_router.mcp_bridge"],
                            "env": {
                                "SWARM_PRIMARY_URL": "http://localhost:4000",
                                "SWARM_PRIMARY_KEY": "your-api-key",
                            },
                        }
                    }
                },
                indent=2,
            )
        )
        return

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
