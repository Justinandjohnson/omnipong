"""Wire message type constants — normative names from RELAY_ARCHITECTURE.md §4.

Kept as plain string constants (not an enum/pydantic model per message type)
because the relay is deliberately content-blind: it dispatches on `type` and
forwards/embeds the rest without validating a strict schema for the opaque
CDP payloads. This is the one place all three surfaces (companion tunnel,
agent HTTP, agent SSE) import their type strings from, so A/B/C can't drift.
"""

# Companion -> Relay, on tunnel open (§4.2)
REGISTER = "REGISTER"

# Relay -> Companion
REGISTER_OK = "REGISTER_OK"
REGISTER_REJECT = "REGISTER_REJECT"
SESSION_START = "SESSION_START"
SESSION_ENDED = "SESSION_ENDED"

# Relay <-> Companion
HEARTBEAT = "HEARTBEAT"

# Relay -> Companion: proxy an HTTP discovery GET (§4.3)
CDP_HTTP_REQ = "CDP_HTTP_REQ"
# Companion -> Relay
CDP_HTTP_RES = "CDP_HTTP_RES"

# Relay -> Companion: open a devtools ws channel to a target
CDP_WS_OPEN = "CDP_WS_OPEN"
# Companion -> Relay
CDP_WS_OPEN_OK = "CDP_WS_OPEN_OK"

# Bi-directional: one opaque CDP protocol frame
CDP_WS_FRAME = "CDP_WS_FRAME"

# Either side closes a channel
CDP_WS_CLOSE = "CDP_WS_CLOSE"

# Gate handshake (§4.4)
GATE_OPEN = "GATE_OPEN"
GATE_CLEARED = "GATE_CLEARED"
GATE_TIMEOUT = "GATE_TIMEOUT"

# SESSION_ENDED reasons (§4.2 / §7)
REASON_COMPLETED = "completed"
REASON_IDLE_TIMEOUT = "idle_timeout"
REASON_MAX_TIMEOUT = "max_timeout"
REASON_GATE_TIMEOUT = "gate_timeout"
REASON_AGENT_ERROR = "agent_error"
REASON_COMPANION_GONE = "companion_gone"
REASON_TAKEOVER = "takeover"

# Gate kinds (§4.4)
GATE_KINDS = frozenset({"login", "cloudflare", "captcha", "twofa", "unknown"})
