"""Relay configuration — all values overridable via environment variables.

One method to load config: read env vars at import time with documented
defaults. No fallback chains, no config file auto-discovery magic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# --- Timeouts (seconds). See RELAY_ARCHITECTURE.md §2.2 / §3.3. ---
IDLE_TTL_S = int(os.environ.get("RELAY_IDLE_TTL_S", "120"))
MAX_TTL_S = int(os.environ.get("RELAY_MAX_TTL_S", "900"))  # 15 min
GATE_TTL_S = int(os.environ.get("RELAY_GATE_TTL_S", "300"))  # 5 min
HEARTBEAT_INTERVAL_S = int(os.environ.get("RELAY_HEARTBEAT_INTERVAL_S", "20"))
# A companion is considered gone if it misses 2x the heartbeat interval.
HEARTBEAT_MISS_LIMIT_S = HEARTBEAT_INTERVAL_S * 2

# Timeout waiting for a companion to answer a proxied CDP HTTP discovery GET
# or a CDP_WS_OPEN_OK ack. This is a relay<->companion round trip over an
# already-open tunnel, so it should be fast; a generous ceiling avoids
# hanging agent-side HTTP calls forever if the companion tunnel is stalled.
COMPANION_RPC_TIMEOUT_S = float(os.environ.get("RELAY_COMPANION_RPC_TIMEOUT_S", "10"))

# --- Registration tokens: register_token -> user_id. ---
# Per RELAY_ARCHITECTURE.md §2.1 this mapping is provisioned out-of-band
# (frontend/account system, out of Agent A's scope). Agent A's only job is
# to consult it. Loaded once from a JSON file: {"rt_...": "u_123", ...}.
# No fallback to guessing / auto-provisioning tokens.
REGISTER_TOKENS_FILE = os.environ.get(
    "RELAY_REGISTER_TOKENS_FILE",
    str(Path(__file__).parent / "register_tokens.json"),
)


def load_register_tokens() -> dict[str, str]:
    path = Path(REGISTER_TOKENS_FILE)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object of {{token: user_id}}")
    return {str(k): str(v) for k, v in data.items()}


HOST = os.environ.get("RELAY_HOST", "0.0.0.0")
PORT = int(os.environ.get("RELAY_PORT", "8765"))

# --- Operator gate (S3 hardening, owner-only posture). ---
# The relay's control endpoints (/session/start, /session/stop, /session/gate)
# are a control plane meant for the owner's own backend/companion only — never
# anonymous callers. No default: unset means the gate fails closed (server.py
# refuses with 503) rather than running open.
OPERATOR_TOKEN = os.environ.get("RELAY_OPERATOR_TOKEN")
