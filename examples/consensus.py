"""
Multi-Model Consensus Example
==============================
Query multiple models in parallel and synthesize their answers
into a single, comprehensive response.
"""

from swarm_router import consensus, SwarmConfig

# Configure with multiple models across tiers
config = SwarmConfig()
config.add_model("gemini-flash", tier="fast", expected_latency_s=3)
config.add_model("deepseek-v3", tier="power", expected_latency_s=8)
config.add_model("gemini-pro", tier="power", expected_latency_s=10)

# --- Basic consensus ---
result = consensus(
    "What are the top 3 emerging risks in AI safety for 2025?",
    config=config,
)

print(f"Consensus from {result['model_count']} models:\n")
print(result["merged"])

# --- Individual responses ---
print("\n--- Individual Responses ---")
for r in result["individual"]:
    status = "OK" if r.get("response") else f"FAIL: {r.get('error', 'unknown')}"
    print(f"  {r['model']}: {status}")

# --- Consensus with system prompt ---
result = consensus(
    "Explain quantum entanglement",
    system="You are a physics teacher explaining to a 12-year-old. Use simple analogies.",
    config=config,
)
print(f"\n--- With System Prompt ---")
print(result["merged"][:500])
