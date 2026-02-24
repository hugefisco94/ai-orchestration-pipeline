"""
Basic Query Example
===================
Send a single query with auto-routing — SwarmRouter picks the best model
based on prompt complexity.
"""

from swarm_router import auto_route, SwarmConfig
from swarm_router.config import Endpoint

# Option 1: Use environment variables (recommended)
# export SWARM_PRIMARY_URL=http://localhost:4000
# export SWARM_PRIMARY_KEY=sk-litellm-master-key
config = SwarmConfig()

# Option 2: Configure programmatically
# config = SwarmConfig(
#     primary=Endpoint(url="http://localhost:4000", api_key="sk-your-key", name="primary")
# )

# Register models by tier
config.add_model("gemini-flash", tier="fast", expected_latency_s=3)
config.add_model("deepseek-v3", tier="power", expected_latency_s=8)
config.add_model("deepseek-r1", tier="deep", expected_latency_s=25)

# --- Simple query (auto-routes to T1 Fast) ---
result = auto_route("What is the capital of France?", config=config)
print(f"Model: {result['model']}")
print(f"Tier:  {result['tier']}")
print(f"Time:  {result['latency_s']}s")
print(f"\n{result['response']}")

# --- Complex query (auto-routes to T3 Deep) ---
result = auto_route(
    "Compare the architectural tradeoffs between microservices and monoliths "
    "for a startup with 5 engineers building a real-time collaboration tool. "
    "Consider deployment complexity, developer velocity, and scaling patterns.",
    config=config,
)
print(f"\n--- Deep Query ---")
print(f"Model: {result['model']} | Tier: {result['tier']} | {result['latency_s']}s")
print(f"\n{result['response']}")

# --- Force a specific tier ---
result = auto_route("Hello!", tier="T2", config=config)
print(f"\n--- Forced T2 ---")
print(f"Model: {result['model']} | {result['response'][:100]}...")
