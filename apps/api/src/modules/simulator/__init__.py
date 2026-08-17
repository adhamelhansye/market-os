"""Deterministic Campaign Simulator (Phase 5A).

What-if simulation engine — given explicit assumptions and historical
evidence, what outcomes would the model produce?

The simulator never claims to know the future. It answers:

  "Given these assumptions and historical evidence, what outcomes
  would the model produce?"

Inputs flow through three explicit deterministic calculation models:

  Model A — CPM → CTR → CVR → AOV
  Model B — CPC → CVR → AOV
  Model C — CPA → AOV

Assumptions are always explicit, versioned, and source-attributed. Outputs
are available/unavailable (never fabricated zeros). No LLM, no autonomous
actions, no provider mutations (see docs/architecture/simulator.md).
"""

from src.modules.simulator import constants, engine, inputs, scenarios, service, validation
from src.modules.simulator.router import router

__all__ = [
    "constants",
    "engine",
    "inputs",
    "router",
    "scenarios",
    "service",
    "validation",
]
