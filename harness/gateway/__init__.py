"""The model gateway: the ONLY place in the harness that talks to an AI model (rule 2).

Everything else calls `Gateway.complete(...)`. See tests/test_one_door.py.
"""
from harness.gateway.gateway import Gateway, GatewayResult  # noqa: F401
from harness.gateway.tiers import Tier, classify  # noqa: F401
