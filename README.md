<div align="center">

# 🌀 SwarmRouter

**Multi-Model AI Orchestration Pipeline**

Route queries to the best AI model. Run parallel consensus. Enrich with knowledge graphs.
One unified interface — any OpenAI-compatible backend.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io)

[Quick Start](#-quick-start) · [Architecture](#-architecture) · [CLI](#-cli-reference) · [API](#-http-api) · [MCP](#-mcp-server) · [Examples](#-examples)

</div>

---

## What is SwarmRouter?

SwarmRouter is a lightweight orchestration layer that sits between your application and multiple LLM providers. Instead of hardcoding a single model, SwarmRouter **automatically routes** queries based on complexity, runs **parallel consensus** across models, and optionally **enriches** prompts with knowledge graph context.

```
Your App → SwarmRouter → LiteLLM / OpenRouter / vLLM / Ollama → Best Result
```

**Key capabilities:**

- **Auto-Routing** — Classifies prompt complexity (T1/T2/T3) and routes to the optimal tier
- **Multi-Model Consensus** — Queries N models in parallel, synthesizes a unified answer
- **Knowledge Pipeline** — Retrieves context from a knowledge graph before generating
- **Health Monitoring** — Thread-safe service health checks with automatic failover
- **MCP Server** — Plug directly into Claude Code, OpenCode, or any MCP client
- **HTTP API** — RESTful endpoints for integration with any language/framework

---

## ⚡ Quick Start

### Install

```bash
pip install swarm-router
```

Or with HTTP server support:

```bash
pip install swarm-router[server]
```

### Configure

Set your LLM proxy endpoint (any OpenAI-compatible API):

```bash
export SWARM_PRIMARY_URL=http://localhost:4000    # LiteLLM, vLLM, etc.
export SWARM_PRIMARY_KEY=sk-your-api-key
```

### Run

```bash
# Single query with auto-routing
swarm-router query "What is quantum computing?"

# Multi-model consensus
swarm-router consensus "Compare React vs Vue for large-scale apps"

# Knowledge-enriched pipeline
swarm-router pipeline "Explain transformer attention mechanisms" --enrich

# Health check
swarm-router health

# Start HTTP API server
swarm-router serve --port 9000
```

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     SwarmRouter                          │
│                                                          │
│  ┌──────────┐   ┌───────────┐   ┌────────────────────┐ │
│  │  Auto-    │   │ Consensus │   │  Knowledge         │ │
│  │  Router   │   │ Engine    │   │  Pipeline          │ │
│  │           │   │           │   │                    │ │
│  │ Classify  │   │ Parallel  │   │ Search → Enrich   │ │
│  │ → Route   │   │ → Merge   │   │ → Generate → Store│ │
│  └─────┬─────┘   └─────┬─────┘   └────────┬──────────┘ │
│        │               │                   │             │
│  ┌─────▼───────────────▼───────────────────▼──────────┐ │
│  │              Tier-Based Model Registry              │ │
│  │                                                     │ │
│  │  T1 (Fast)     T2 (Power)       T3 (Deep)         │ │
│  │  gemini-flash  deepseek-v3      deepseek-r1        │ │
│  │  qwen3-coder   gemini-pro       o1 / claude-opus   │ │
│  │  mistral-small claude-haiku     qwen3-235b         │ │
│  └────────┬────────────┬───────────────┬──────────────┘ │
│           │            │               │                 │
└───────────┼────────────┼───────────────┼─────────────────┘
            │            │               │
     ┌──────▼──────┐ ┌──▼──────┐ ┌──────▼──────┐
     │  LiteLLM    │ │ OpenAI  │ │  Knowledge  │
     │  Proxy      │ │ Router  │ │  Graph      │
     │  :4000      │ │  API    │ │  (Cognee)   │
     └─────────────┘ └─────────┘ └─────────────┘
```

### Complexity Tiers

| Tier | Use Case | Latency | Models |
|------|----------|---------|--------|
| **T1 Fast** | Simple lookups, translations, formatting | 2-10s | gemini-flash, qwen3-coder, mistral-small |
| **T2 Power** | Analysis, coding, multi-step reasoning | 5-15s | deepseek-v3, gemini-pro, claude-haiku |
| **T3 Deep** | Research, architecture, complex reasoning | 15-60s | deepseek-r1, qwen3-235b |

Complexity is auto-detected from prompt length and keywords, or manually specified.

---

## 🔧 Configuration

All configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SWARM_PRIMARY_URL` | Primary LLM proxy URL | `http://localhost:4000` |
| `SWARM_PRIMARY_KEY` | Primary API key | `sk-default` |
| `SWARM_SECONDARY_URL` | Secondary endpoint (optional) | — |
| `SWARM_SECONDARY_KEY` | Secondary API key | — |
| `SWARM_KNOWLEDGE_URL` | Knowledge graph API (optional) | — |
| `SWARM_TIMEOUT_FAST` | Fast tier timeout (seconds) | `30` |
| `SWARM_TIMEOUT_POWER` | Power tier timeout (seconds) | `60` |
| `SWARM_TIMEOUT_DEEP` | Deep tier timeout (seconds) | `120` |

### Programmatic Configuration

```python
from swarm_router import SwarmConfig

config = SwarmConfig()
config.add_model("openrouter/google/gemini-flash-2.0", tier="fast", expected_latency_s=3)
config.add_model("openrouter/deepseek/deepseek-chat", tier="power", expected_latency_s=8)
config.add_model("openrouter/deepseek/deepseek-r1", tier="deep", expected_latency_s=25)
```

---

## 📖 CLI Reference

```
swarm-router <command> [options]
```

| Command | Description |
|---------|-------------|
| `health` | Check all backend service health |
| `query <prompt>` | Single query with auto-routing |
| `consensus <prompt>` | Multi-model parallel consensus |
| `pipeline <prompt>` | Knowledge-enriched generation pipeline |
| `serve` | Start the HTTP API server |

### Examples

```bash
# Force a specific complexity tier
swarm-router query "Explain attention" --tier T2

# Knowledge pipeline with storage
swarm-router pipeline "Latest advances in protein folding" --enrich --store

# Pipeline with consensus generation
swarm-router pipeline "Compare CRISPR vs base editing" --enrich --consensus

# Start server on custom port
swarm-router serve --port 8080
```

---

## 🌐 HTTP API

Start the server:

```bash
swarm-router serve --port 9000
```

### Endpoints

#### `GET /health`

```bash
curl http://localhost:9000/health
```

```json
{
  "status": "ok",
  "services": {"primary": true, "secondary": true, "knowledge": true}
}
```

#### `POST /v1/query`

```bash
curl -X POST http://localhost:9000/v1/query \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is quantum computing?", "tier": "T1"}'
```

```json
{
  "model": "openrouter/google/gemini-flash-2.0",
  "tier": "fast",
  "response": "Quantum computing uses quantum-mechanical phenomena...",
  "latency_s": 2.34
}
```

#### `POST /v1/consensus`

```bash
curl -X POST http://localhost:9000/v1/consensus \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Compare React vs Vue for enterprise apps"}'
```

#### `POST /v1/pipeline`

```bash
curl -X POST http://localhost:9000/v1/pipeline \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain CRISPR mechanisms", "enrich": true, "store": true}'
```

---

## 🔌 MCP Server

Connect SwarmRouter directly to Claude Code or any MCP-compatible client.

### Setup in Claude Code

Add to your `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "swarm-router": {
      "command": "python",
      "args": ["-m", "swarm_router.mcp_bridge"],
      "env": {
        "SWARM_PRIMARY_URL": "http://localhost:4000",
        "SWARM_PRIMARY_KEY": "sk-your-api-key"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `swarm_query` | Route a query to the best model (auto-complexity) |
| `swarm_call` | Call multiple models in parallel by tier |
| `swarm_status` | Check health of all connected services |

### Print Config Snippet

```bash
python -m swarm_router.mcp_bridge --print-config
```

---

## 🐳 Docker

### Standalone

```bash
docker build -t swarm-router .
docker run -p 9000:9000 \
  -e SWARM_PRIMARY_URL=http://host.docker.internal:4000 \
  -e SWARM_PRIMARY_KEY=sk-your-key \
  swarm-router
```

### Docker Compose (with LiteLLM)

```bash
docker compose up -d
```

See [`docker-compose.yml`](docker-compose.yml) for a complete setup with LiteLLM proxy included.

---

## 📚 Examples

### Basic Query (Python)

```python
from swarm_router import auto_route, SwarmConfig

config = SwarmConfig()
config.add_model("gpt-4o", tier="power")

result = auto_route("Explain recursion in 3 sentences", config=config)
print(f"[{result['model']}] {result['response']}")
```

### Multi-Model Consensus

```python
from swarm_router import consensus, SwarmConfig

config = SwarmConfig()
config.add_model("gpt-4o", tier="power")
config.add_model("claude-sonnet-4-20250514", tier="power")
config.add_model("gemini-pro", tier="power")

result = consensus("What are the top 3 risks of AGI?", config=config)
print(result["merged"])
```

### Async Swarm Call

```python
import asyncio
from swarm_router import swarm_call, SwarmConfig

config = SwarmConfig()
config.add_model("gemini-flash", tier="fast", expected_latency_s=3)
config.add_model("qwen3-coder", tier="fast", expected_latency_s=5)
config.add_model("mistral-small", tier="fast", expected_latency_s=9)

async def main():
    results = await swarm_call("Hello world!", tier="fast", config=config)
    for r in results:
        print(f"{r['model']}: {r['status']} ({r['elapsed_s']}s)")

asyncio.run(main())
```

### Knowledge Pipeline

```python
from swarm_router import pipeline, SwarmConfig

config = SwarmConfig()
config.add_model("deepseek-v3", tier="power")

result = pipeline(
    "What are recent advances in protein structure prediction?",
    enrich=True,   # Search knowledge graph first
    store=True,    # Store Q&A back to knowledge graph
    config=config,
)
print(f"Context used: {result['context_results_count']} results")
print(result["answer"])
```

---

## 🛣 Roadmap

- [ ] Streaming responses (SSE)
- [ ] Token budget management
- [ ] Model performance tracking & auto-reranking
- [ ] Built-in rate limiting
- [ ] WebSocket support
- [ ] Plugin system for custom routing strategies

---

## 🤝 Contributing

Contributions welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
<sub>Built with ❤️ for the AI orchestration community</sub>
</div>
