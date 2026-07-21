"""Message-type constants for the companion <-> relay tunnel.

Schema source of truth: docs/RELAY_ARCHITECTURE.md §4 (message schemas).
Field names here must match that doc exactly — no local reinterpretation.
"""

# §4.2 registration & lifecycle
REGISTER = "REGISTER"
REGISTER_OK = "REGISTER_OK"
REGISTER_REJECT = "REGISTER_REJECT"
SESSION_START = "SESSION_START"
HEARTBEAT = "HEARTBEAT"
SESSION_ENDED = "SESSION_ENDED"

# §4.3 CDP tunnel frames
CDP_HTTP_REQ = "CDP_HTTP_REQ"
CDP_HTTP_RES = "CDP_HTTP_RES"
CDP_WS_OPEN = "CDP_WS_OPEN"
CDP_WS_OPEN_OK = "CDP_WS_OPEN_OK"
CDP_WS_FRAME = "CDP_WS_FRAME"
CDP_WS_CLOSE = "CDP_WS_CLOSE"

# §4.4 gate handshake
GATE_OPEN = "GATE_OPEN"
GATE_CLEARED = "GATE_CLEARED"
GATE_TIMEOUT = "GATE_TIMEOUT"

COMPANION_VERSION = "0.1.0"
