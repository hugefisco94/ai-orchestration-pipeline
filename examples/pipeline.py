"""
Knowledge Pipeline Example
===========================
Search a knowledge graph for context, enrich the prompt, generate an answer,
and optionally store the result back.

Requires a knowledge graph backend (e.g., Cognee) running.
Set SWARM_KNOWLEDGE_URL to enable.
"""

from swarm_router import pipeline, SwarmConfig

# Configure endpoints
config = SwarmConfig()
config.add_model("deepseek-v3", tier="power", expected_latency_s=8)

# If you have a knowledge graph running:
# export SWARM_KNOWLEDGE_URL=http://localhost:8080/api/v1

# --- Basic pipeline (no knowledge enrichment) ---
result = pipeline(
    "What are recent advances in protein structure prediction?",
    enrich=False,
    store=False,
    config=config,
)
print(f"Model: {result['model_info']}")
print(f"Latency: {result['total_latency_s']}s")
print(f"\n{result['answer']}")

# --- Knowledge-enriched pipeline ---
# This searches the knowledge graph first, enriches the prompt with context,
# then generates the answer, and stores the Q&A pair back.
result = pipeline(
    "How does AlphaFold3 differ from AlphaFold2?",
    enrich=True,  # Search knowledge graph for context
    store=True,  # Store result back to knowledge graph
    config=config,
)
print(f"\n--- Enriched Pipeline ---")
print(f"Context results: {result['context_results_count']}")
print(f"Latency: {result['total_latency_s']}s")
print(f"Stored: {result['stored']}")
print(f"\n{result['answer']}")

# --- Pipeline with consensus ---
# Uses multi-model consensus instead of single auto-route
result = pipeline(
    "Compare CRISPR-Cas9 vs base editing for therapeutic applications",
    enrich=True,
    store=True,
    use_consensus=True,
    config=config,
)
print(f"\n--- Consensus Pipeline ---")
print(
    f"Context: {result['context_results_count']} | Latency: {result['total_latency_s']}s"
)
print(f"\n{result['answer'][:1000]}...")
