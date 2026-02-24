"""SwarmRouter — Multi-model AI orchestration pipeline."""

__version__ = "0.1.0"

from swarm_router.config import SwarmConfig
from swarm_router.orchestrator import auto_route, consensus, pipeline
from swarm_router.swarm import swarm_call, call_model, rank_results
from swarm_router.health import ServiceHealth

__all__ = [
    "SwarmConfig",
    "auto_route",
    "consensus",
    "pipeline",
    "swarm_call",
    "call_model",
    "rank_results",
    "ServiceHealth",
]
