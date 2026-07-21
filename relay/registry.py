"""In-memory session/companion registry — the relay's only state store.

Deliberately in-memory (per RELAY_ARCHITECTURE.md §2.1: "in-memory (or small
KV)"). The relay holds no credentials and no page content, so losing this
state on restart is an acceptable, documented trade-off (companions
reconnect and re-register; in-flight sessions are lost, which is the same
failure shape as F1/F3 in §7). Swapping in a KV store later is a storage-
layer change, not a protocol change — nothing above this module needs to
know.
"""

from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

# Framework-agnostic: registry.py has no FastAPI/Starlette import. The
# companion's live websocket handle is stashed as Any so server.py can force-
# close it from the heartbeat watcher without this module depending on ASGI.

from errors import CompanionNotOnline, SessionConflict, UnknownGate, UnknownSession

# A companion's outbound send is duck-typed: anything with an async
# `send_json_to_companion(dict) -> None`. server.py supplies the real
# Starlette WebSocket-backed implementation; tests supply a fake.
SendFn = Callable[[dict], Awaitable[None]]


@dataclass
class Companion:
    register_token: str
    user_id: str
    send: SendFn
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    online: bool = True
    websocket: Any = None  # set by server.py; used only to force-close on a missed heartbeat

    # Per-channel demux for the CDP devtools websockets multiplexed over
    # this companion's single tunnel (§1.3/§4.3). One companion has at most
    # one active session, so channel numbering resets per session.
    next_channel: int = 1
    agent_ws_send: dict[int, SendFn] = field(default_factory=dict)

    # Pending RPCs waiting on a companion reply, keyed by req_id / channel.
    pending_http: dict[str, "asyncio.Future[dict]"] = field(default_factory=dict)
    pending_ws_open: dict[int, "asyncio.Future[None]"] = field(default_factory=dict)

    def allocate_channel(self) -> int:
        ch = self.next_channel
        self.next_channel += 1
        return ch


@dataclass
class Gate:
    gate_id: str
    session_id: str
    kind: str
    hint: str
    url_host: str
    created_at: float = field(default_factory=time.time)
    cleared: asyncio.Event = field(default_factory=asyncio.Event)
    timed_out: bool = False
    timeout_task: Optional[asyncio.Task] = None


@dataclass
class Session:
    session_id: str
    session_token: str
    user_id: str
    companion: Companion
    created_at: float = field(default_factory=time.time)
    last_cdp_activity: float = field(default_factory=time.time)
    ended: bool = False
    end_reason: Optional[str] = None
    gates: dict[str, Gate] = field(default_factory=dict)
    # gate_ids currently OPEN (not yet cleared or timed out). Non-empty means
    # the idle watcher must not reap this session — GATE_TTL governs instead
    # (C1: no CDP frames flow while a gate is open, by design).
    open_gate_ids: set[str] = field(default_factory=set)
    # Push-back events for the agent's SSE stream (§8.3 / GET /session/events).
    events: "asyncio.Queue[dict]" = field(default_factory=asyncio.Queue)
    idle_task: Optional[asyncio.Task] = None
    max_task: Optional[asyncio.Task] = None

    def touch(self) -> None:
        self.last_cdp_activity = time.time()


class Registry:
    """All relay state. One instance per process; no external dependency."""

    def __init__(self) -> None:
        self.register_tokens: dict[str, str] = {}
        self.companions_by_user_id: dict[str, Companion] = {}
        self.sessions_by_token: dict[str, Session] = {}
        self.sessions_by_user_id: dict[str, Session] = {}

    def load_register_tokens(self, tokens: dict[str, str]) -> None:
        self.register_tokens = dict(tokens)

    # -- Companion lifecycle -------------------------------------------------

    def resolve_register_token(self, register_token: str) -> Optional[str]:
        return self.register_tokens.get(register_token)

    def register_companion(self, register_token: str, user_id: str, send: SendFn) -> Companion:
        companion = Companion(register_token=register_token, user_id=user_id, send=send)
        self.companions_by_user_id[user_id] = companion
        return companion

    def unregister_companion(self, companion: Companion) -> Optional[Session]:
        """Mark a companion offline and return its bound session, if any."""
        companion.online = False
        if self.companions_by_user_id.get(companion.user_id) is companion:
            del self.companions_by_user_id[companion.user_id]
        return self.sessions_by_user_id.get(companion.user_id)

    def get_online_companion(self, user_id: str) -> Companion:
        companion = self.companions_by_user_id.get(user_id)
        if companion is None or not companion.online:
            raise CompanionNotOnline(f"no online companion for user_id={user_id!r}")
        return companion

    # -- Session lifecycle -----------------------------------------------------

    def start_session(self, user_id: str, companion: Companion, takeover: bool) -> Session:
        existing = self.sessions_by_user_id.get(user_id)
        if existing is not None and not existing.ended:
            if not takeover:
                raise SessionConflict(
                    f"user_id={user_id!r} already has an active session "
                    f"(session_id={existing.session_id!r}); pass takeover=true to replace it"
                )
            existing.ended = True
            existing.end_reason = "takeover"

        session = Session(
            session_id=f"s_{uuid.uuid4().hex[:12]}",
            session_token=f"st_{secrets.token_urlsafe(32)}",
            user_id=user_id,
            companion=companion,
        )
        self.sessions_by_token[session.session_token] = session
        self.sessions_by_user_id[user_id] = session
        companion.next_channel = 1
        companion.agent_ws_send.clear()
        return session

    def get_session(self, session_token: str) -> Session:
        session = self.sessions_by_token.get(session_token)
        if session is None or session.ended:
            raise UnknownSession(f"no active session for session_token")
        return session

    def end_session(self, session: Session, reason: str) -> None:
        if session.ended:
            return
        session.ended = True
        session.end_reason = reason
        for task in (session.idle_task, session.max_task):
            if task is not None:
                task.cancel()
        for gate in session.gates.values():
            if gate.timeout_task is not None:
                gate.timeout_task.cancel()
        if self.sessions_by_token.get(session.session_token) is session:
            del self.sessions_by_token[session.session_token]
        if self.sessions_by_user_id.get(session.user_id) is session:
            del self.sessions_by_user_id[session.user_id]

    # -- Gate lifecycle ----------------------------------------------------

    def open_gate(self, session: Session, gate_id: str, kind: str, hint: str, url_host: str) -> Gate:
        gate = Gate(gate_id=gate_id, session_id=session.session_id, kind=kind, hint=hint, url_host=url_host)
        session.gates[gate_id] = gate
        session.open_gate_ids.add(gate_id)
        session.touch()
        return gate

    def get_gate(self, session: Session, gate_id: str) -> Gate:
        gate = session.gates.get(gate_id)
        if gate is None:
            raise UnknownGate(f"no gate {gate_id!r} on session {session.session_id!r}")
        return gate

    def clear_gate(self, session: Session, gate_id: str) -> Gate:
        gate = self.get_gate(session, gate_id)
        gate.cleared.set()
        if gate.timeout_task is not None:
            gate.timeout_task.cancel()
        session.open_gate_ids.discard(gate_id)
        session.touch()
        return gate
