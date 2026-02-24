"""
SwarmRouter Configuration
========================
All configuration via environment variables with sensible defaults.
Supports any OpenAI-compatible endpoint (LiteLLM, vLLM, OpenRouter, etc.)
"""

import os
from dataclasses import dataclass, field


@dataclass
class Endpoint:
    """An LLM API endpoint."""

    url: str
    api_key: str
    name: str = ""


@dataclass
class ModelEntry:
    """A model registered in the swarm."""

    model_id: str
    tier: str  # "fast", "power", "deep"
    endpoint: Endpoint
    expected_latency_s: float = 10.0


@dataclass
class SwarmConfig:
    """
    Central configuration for SwarmRouter.

    Reads from environment variables:
        SWARM_PRIMARY_URL       Primary LLM proxy URL (default: http://localhost:4000)
        SWARM_PRIMARY_KEY       Primary API key (default: sk-default)
        SWARM_SECONDARY_URL     Secondary endpoint URL (optional, e.g. Elice Cloud)
        SWARM_SECONDARY_KEY     Secondary API key (optional)
        SWARM_KNOWLEDGE_URL     Knowledge graph API URL (optional, e.g. Cognee)
        SWARM_TIMEOUT_FAST      Fast tier timeout seconds (default: 30)
        SWARM_TIMEOUT_POWER     Power tier timeout seconds (default: 60)
        SWARM_TIMEOUT_DEEP      Deep tier timeout seconds (default: 120)

    Models can be registered programmatically or via add_model().
    """

    primary: Endpoint = field(
        default_factory=lambda: Endpoint(
            url=os.environ.get("SWARM_PRIMARY_URL", "http://localhost:4000"),
            api_key=os.environ.get("SWARM_PRIMARY_KEY", "sk-default"),
            name="primary",
        )
    )

    secondary: Endpoint | None = field(default=None)
    knowledge_url: str | None = field(default=None)

    timeout_fast: tuple[float, float] = field(default=(5, 30))
    timeout_power: tuple[float, float] = field(default=(5, 60))
    timeout_deep: tuple[float, float] = field(default=(5, 120))

    models: list[ModelEntry] = field(default_factory=list)

    # Complexity classification thresholds
    t1_max_words: int = 20
    t2_max_words: int = 60
    deep_keywords: set[str] = field(
        default_factory=lambda: {
            "compare",
            "analyze",
            "tradeoffs",
            "architecture",
            "design",
            "research",
            "explain in detail",
            "step by step",
            "why",
            "how does",
            "evaluate",
            "pros and cons",
            "difference between",
        }
    )

    def __post_init__(self):
        # Auto-configure secondary endpoint from env
        sec_url = os.environ.get("SWARM_SECONDARY_URL")
        sec_key = os.environ.get("SWARM_SECONDARY_KEY")
        if sec_url and sec_key and self.secondary is None:
            self.secondary = Endpoint(url=sec_url, api_key=sec_key, name="secondary")

        # Auto-configure knowledge URL from env
        if self.knowledge_url is None:
            self.knowledge_url = os.environ.get("SWARM_KNOWLEDGE_URL")

        # Parse timeout overrides
        tf = os.environ.get("SWARM_TIMEOUT_FAST")
        if tf:
            self.timeout_fast = (5, float(tf))
        tp = os.environ.get("SWARM_TIMEOUT_POWER")
        if tp:
            self.timeout_power = (5, float(tp))
        td = os.environ.get("SWARM_TIMEOUT_DEEP")
        if td:
            self.timeout_deep = (5, float(td))

    def add_model(
        self,
        model_id: str,
        tier: str = "fast",
        endpoint: Endpoint | None = None,
        expected_latency_s: float = 10.0,
    ) -> "SwarmConfig":
        """Register a model. Returns self for chaining."""
        ep = endpoint or self.primary
        self.models.append(
            ModelEntry(
                model_id=model_id,
                tier=tier,
                endpoint=ep,
                expected_latency_s=expected_latency_s,
            )
        )
        return self

    def get_tier_models(self, tier: str) -> list[ModelEntry]:
        """Get models for a specific tier."""
        return [m for m in self.models if m.tier == tier]

    def get_tier_timeout(self, tier: str) -> tuple[float, float]:
        """Get timeout for a tier."""
        return {
            "T1": self.timeout_fast,
            "T2": self.timeout_power,
            "T3": self.timeout_deep,
            "fast": self.timeout_fast,
            "power": self.timeout_power,
            "deep": self.timeout_deep,
        }.get(tier, self.timeout_power)

    def classify_complexity(self, prompt: str) -> str:
        """Classify prompt complexity into T1/T2/T3."""
        words = len(prompt.split())
        has_deep = any(kw in prompt.lower() for kw in self.deep_keywords)
        if has_deep or words > self.t2_max_words:
            return "T3"
        if words > self.t1_max_words:
            return "T2"
        return "T1"


# ---------------------------------------------------------------------------
# Factory: create a default config matching the reference implementation
# ---------------------------------------------------------------------------


def default_config() -> SwarmConfig:
    """
    Create a SwarmConfig from environment variables.

    Set these env vars for full functionality:
        SWARM_PRIMARY_URL=http://localhost:4000
        SWARM_PRIMARY_KEY=sk-litellm-master-key
        SWARM_SECONDARY_URL=http://localhost:8100
        SWARM_SECONDARY_KEY=sk-elice-litellm-key
        SWARM_KNOWLEDGE_URL=http://localhost:8080/api/v1
    """
    cfg = SwarmConfig()

    # If no models registered, add defaults from env or skip
    if not cfg.models and cfg.primary.api_key != "sk-default":
        # Register a generic model on the primary endpoint
        cfg.add_model("default", tier="fast", expected_latency_s=5.0)

    return cfg
