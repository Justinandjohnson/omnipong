from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import subprocess
import asyncio
import os
import sys

import anthropic
import httpx
import json
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env variables
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

# Configurable player identity so anyone can run this — defaults are generic.
PLAYER_NAME = os.getenv("PLAYER_NAME", "the player")
PLAYER_FULL_NAME = os.getenv("PLAYER_FULL_NAME", PLAYER_NAME)

# Add project root to path so we can import browser_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from browser_manager import BrowserManager

# Import shared utilities
from .tournament_intelligence import get_tournament_intelligence
from models import Activity, Event, Notification, Base


# Initialize models
class ChatMessage(BaseModel):
    message: str


class PlayerSearch(BaseModel):
    name: str = None


class ProcessText(BaseModel):
    text: str


class StadiumSyncStartRequest(BaseModel):
    """Request body for the Tier-3 sync-start endpoints (/tools/sync/stadium,
    /tools/sync/omnipong). Matches the frontend contract documented in
    StadiumSyncPanel.tsx: { player_name }. There is no session_token here —
    F provisions the relay session itself (see _provision_relay_session);
    the frontend/companion never hands F a raw CDP session token directly."""

    player_name: str | None = None
    model: str | None = None


# --- Tier-3/Tier-1 browser-agent bridge ---
# Frozen interface: docs/RELAY_ARCHITECTURE.md §8 (B<->F). F calls
# run_browser_task(...); F does not build cdp_url or talk CDP directly — that's
# Agent B's module. Import is guarded because browser_agent.py may not exist yet
# while B is still building it; callers get a clean 503, not a silent fallback.
try:
    from .browser_agent import run_browser_task, validate_player_name, validate_task_text

    BROWSER_AGENT_AVAILABLE = True
    _browser_agent_import_error = None
except ImportError as e:
    BROWSER_AGENT_AVAILABLE = False
    _browser_agent_import_error = str(e)
    run_browser_task = None
    validate_player_name = None
    validate_task_text = None


def _get_user_openrouter_key(request: Request) -> str | None:
    """BYOK OpenRouter key for browser-agent calls.

    OQ-4 (RELAY_ARCHITECTURE.md §6 / BROWSER_USE_SPIKE.md): reuses the same
    `X-User-Api-Key` header the frontend already sends for the Anthropic key
    (DemoBar.tsx's single BYOK field accepts either an Anthropic `sk-ant-...`
    or OpenRouter `sk-or-...` key today, and StadiumSyncPanel.tsx already
    forwards it via getAIHeaders()). The spike's recommendation to split this
    into a distinct `X-User-OpenRouter-Key` header was explicitly "not
    implemented, a recommendation for E/F to adopt" — since E's frontend
    ships one BYOK field and both E and F already agree on this single
    header, there is no actual Phase-1 drift here to reconcile, so Phase 2
    leaves it as-is rather than force a frontend change for no behavior gain.
    """
    return request.headers.get("X-User-Api-Key") or None


def _browser_task_error(result) -> JSONResponse:
    """Map a non-ok BrowserTaskResult to the frozen §7 error shape:
    {"error": {"type": ..., "detail": ...}}. No fallback — if browser_agent's
    result doesn't carry a compatible `.error` dict, that's a clean 500, not a
    guessed shape."""
    error = getattr(result, "error", None)
    if not isinstance(error, dict) or "type" not in error or "detail" not in error:
        raise HTTPException(
            status_code=500,
            detail="browser_agent returned a non-ok result without a valid {type, detail} error payload",
        )
    return JSONResponse(status_code=502, content={"error": error})


def _relay_operator_headers() -> dict:
    """S3: the relay's own control endpoints (/session/start, /session/stop,
    /session/gate) are gated behind RELAY_OPERATOR_TOKEN (relay/config.py's
    OPERATOR_TOKEN, checked by relay/server.py's _require_operator_token).
    This backend is the relay's one legitimate caller, so it must present
    the same token. If unset here, the relay's own fail-closed check (503)
    is what surfaces the misconfiguration — this helper does not duplicate
    that check, it just forwards whatever is configured."""
    token = os.getenv("RELAY_OPERATOR_TOKEN")
    return {"X-Operator-Token": token} if token else {}


async def _provision_relay_session(register_token: str, *, relay_base_url: str) -> str:
    """Mint a fresh relay session_token via POST /session/start
    (RELAY_ARCHITECTURE.md §2.2) for the given register_token.

    Seam: 'who calls relay /session/start' (Phase 2 seam #2) — F does, right
    before each browser-agent run, using a register_token read from server
    config (never from the frontend). One relay round trip, no retries: any
    rejection (bad token, companion not online, one-browser-per-user
    conflict) surfaces as a single clean HTTPException.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{relay_base_url.rstrip('/')}/session/start",
                json={"register_token": register_token},
                headers=_relay_operator_headers(),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not reach the relay to start a session: {exc}"
        ) from exc

    if resp.status_code != 200:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        raise HTTPException(status_code=502, detail=f"Relay refused to start a session: {detail}")

    session_token = resp.json().get("session_token")
    if not session_token:
        raise HTTPException(status_code=502, detail="Relay /session/start response missing session_token")
    return session_token


async def _stop_relay_session(session_token: str, *, relay_base_url: str) -> None:
    """E3: POST /session/start (§2.2) sessions were only ever being reaped by
    IDLE_TTL_S (120s), blocking an immediate re-sync with a 409 SessionConflict
    in the meantime. Call this once run_browser_task has returned so the
    session ends right away instead. Best-effort: the relay tears sessions
    down on its own regardless, so a failure here is logged, not raised."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{relay_base_url.rstrip('/')}/session/stop",
                json={"session_token": session_token},
                headers=_relay_operator_headers(),
            )
    except httpx.HTTPError as exc:
        print(f"[relay] /session/stop failed for session_token={session_token!r}: {exc}")


async def _run_browser_agent_task(
    *, task: str, site: str, player_name: str, session_token: str, model: str | None, request: Request
):
    """Shared call path into Agent B's run_browser_task for the synchronous
    Tier-1 (public, no personal login) lookup flow."""
    if not BROWSER_AGENT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"browser_agent module not available yet: {_browser_agent_import_error}",
        )

    # S2: same charset/length/control-char rules as browser_agent's own
    # run_browser_task boundary, enforced again here at the request boundary.
    name_error = validate_player_name(player_name)
    if name_error:
        raise HTTPException(status_code=400, detail=f"Invalid player_name: {name_error}")
    task_error = validate_task_text(task)
    if task_error:
        raise HTTPException(status_code=400, detail=f"Invalid task: {task_error}")

    openrouter_key = _get_user_openrouter_key(request)
    if not openrouter_key:
        raise HTTPException(
            status_code=401,
            detail="Missing BYOK key (X-User-Api-Key header) — required as the OpenRouter key for the browser agent.",
        )

    relay_base_url = os.getenv("RELAY_BASE_URL")
    if not relay_base_url:
        raise HTTPException(status_code=500, detail="RELAY_BASE_URL is not configured on the server.")

    return await run_browser_task(
        task=task,
        site=site,
        player_name=player_name,
        session_token=session_token,
        openrouter_key=openrouter_key,
        model=model or os.getenv("BROWSER_AGENT_MODEL", "google/gemini-3-pro-preview"),
        relay_base_url=relay_base_url,
    )


# --- Tier-3 gate-event SSE bridge (Phase 2 seam #1) ---
#
# There are two SSE layers in this platform: relay -> Agent B (B's
# RelayGateClient, already wired against relay/server.py's
# /session/events/{session_token}) and Agent F -> frontend
# (StadiumSyncPanel.tsx's GET /tools/sync/stadium/events/{session_id}).
# This module bridges them with one asyncio.Queue per in-flight sync,
# keyed by session_id (we reuse the relay's session_token as that id — it is
# not a credential, RELAY_ARCHITECTURE.md §5, and reusing it avoids a second
# id-mapping table). run_browser_task's on_gate callback pushes
# gate_open/gate_cleared/gate_timeout onto the queue; the SSE endpoint drains
# it and formats each item as a named SSE event, ending on "done" or
# "gate_timeout" per the frontend's own stream-closing logic.
_sync_event_queues: dict[str, "asyncio.Queue[tuple[str, dict]]"] = {}


async def _run_and_stream_browser_task(
    *,
    session_id: str,
    task: str,
    site: str,
    player_name: str,
    session_token: str,
    model: str | None,
    openrouter_key: str,
    relay_base_url: str,
) -> None:
    """Runs run_browser_task in the background and streams its gate events +
    final result onto _sync_event_queues[session_id]. This is a detached
    asyncio.Task with no caller to propagate exceptions to, so the outer
    try/except is not a fallback path — it is the one way to turn an
    otherwise-swallowed exception into the single terminal SSE event the
    frontend is waiting on, so the stream always terminates."""
    queue = _sync_event_queues[session_id]

    async def on_gate(evt: dict) -> None:
        await queue.put(
            (evt["event"], {"gate_id": evt["gate_id"], "kind": evt["kind"], "hint": evt["hint"], "url_host": evt["url_host"]})
        )

    try:
        result = await run_browser_task(
            task=task,
            site=site,
            player_name=player_name,
            session_token=session_token,
            openrouter_key=openrouter_key,
            model=model or os.getenv("BROWSER_AGENT_MODEL", "google/gemini-3-pro-preview"),
            relay_base_url=relay_base_url,
            on_gate=on_gate,
        )
    except Exception as exc:  # noqa: BLE001 - see docstring: terminates the SSE stream cleanly
        await queue.put(
            ("done", {"status": "llm_error", "matches": [], "steps_used": 0, "error": {"type": type(exc).__name__, "detail": str(exc)}})
        )
        await _stop_relay_session(session_token, relay_base_url=relay_base_url)  # E3
        _sync_event_queues.pop(session_id, None)  # E4: also reached if the SSE side never connects
        return

    await queue.put(
        ("done", {"status": result.status, "matches": result.matches, "steps_used": result.steps_used, "error": result.error})
    )
    await _stop_relay_session(session_token, relay_base_url=relay_base_url)  # E3
    _sync_event_queues.pop(session_id, None)  # E4: also reached if the SSE side never connects


async def _start_tier3_sync(*, task: str, site: str, player_name: str, model: str | None, request: Request) -> dict:
    """Provisions a relay session, kicks off the browser-agent run in the
    background, and returns {"session_id": ...} immediately — matching
    StadiumSyncPanel.tsx's contract (POST resp: { session_id } | { error })."""
    if not BROWSER_AGENT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"browser_agent module not available yet: {_browser_agent_import_error}",
        )

    # S2: same charset/length/control-char rules as browser_agent's own
    # run_browser_task boundary, enforced again here at the request boundary
    # — before a relay session is minted for a bad name.
    name_error = validate_player_name(player_name)
    if name_error:
        raise HTTPException(status_code=400, detail=f"Invalid player_name: {name_error}")
    task_error = validate_task_text(task)
    if task_error:
        raise HTTPException(status_code=400, detail=f"Invalid task: {task_error}")

    openrouter_key = _get_user_openrouter_key(request)
    if not openrouter_key:
        raise HTTPException(
            status_code=401,
            detail="Missing BYOK key (X-User-Api-Key header) — required as the OpenRouter key for the browser agent.",
        )

    relay_base_url = os.getenv("RELAY_BASE_URL")
    if not relay_base_url:
        raise HTTPException(status_code=500, detail="RELAY_BASE_URL is not configured on the server.")

    register_token = os.getenv("RELAY_REGISTER_TOKEN")
    if not register_token:
        raise HTTPException(
            status_code=503,
            detail="No companion registered (RELAY_REGISTER_TOKEN unset) — launch your companion first, see docs/PLATFORM_RUNBOOK.md.",
        )

    session_token = await _provision_relay_session(register_token, relay_base_url=relay_base_url)
    session_id = session_token
    _sync_event_queues[session_id] = asyncio.Queue()

    asyncio.create_task(
        _run_and_stream_browser_task(
            session_id=session_id,
            task=task,
            site=site,
            player_name=player_name,
            session_token=session_token,
            model=model,
            openrouter_key=openrouter_key,
            relay_base_url=relay_base_url,
        )
    )
    return {"session_id": session_id}


def _sse_response_for_sync_session(session_id: str) -> StreamingResponse:
    queue = _sync_event_queues.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail=f"Unknown or expired sync session_id={session_id!r}")

    async def _stream():
        try:
            while True:
                try:
                    event_name, data = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # C2: keep the stream alive through Cloudflare's ~100s idle
                    # cutoff during a silent gate wait.
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {event_name}\ndata: {json.dumps(data)}\n\n"
                if event_name in ("done", "gate_timeout"):
                    return
        finally:
            _sync_event_queues.pop(session_id, None)

    return StreamingResponse(_stream(), media_type="text/event-stream")


# Initialize BrowserManager for tools
browser_manager = BrowserManager()

# Global list to track active subprocesses
active_processes = []


async def run_script_managed(script_path: str, args: list = None, cwd: str = None):
    """Helper to run a script, track it, and clean up after."""
    if args is None:
        args = []
    if cwd is None:
        cwd = os.path.dirname(script_path)

    try:
        process = await asyncio.create_subprocess_exec(
            "python3",
            script_path,
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
        )
        active_processes.append(process)

        stdout, stderr = await process.communicate()

        # Cleanup
        if process in active_processes:
            active_processes.remove(process)

        return process.returncode, stdout, stderr
    except Exception as e:
        # Attempt cleanup if something failed during setup
        return -1, b"", str(e).encode()


app = FastAPI(title="Rubberr — Table Tennis Intelligence")

_LOCAL_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_LOCAL_ORIGINS,
    allow_origin_regex=r"https://(.*\.onrender\.com|.*\.vercel\.app)",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_user_ai_key(request: Request) -> str | None:
    """Return the user-supplied AI key from the X-User-Api-Key header."""
    return request.headers.get("X-User-Api-Key") or None


def _require_api_key(request: Request) -> None:
    """Raise 401 if RUBBERR_API_KEY env var is set and request doesn't match."""
    required = os.getenv("RUBBERR_API_KEY")
    if not required:
        return
    provided = request.headers.get("X-Api-Key")
    if provided != required:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_operator_token(request: Request) -> None:
    """S1 hardening: owner-only gate on the Tier-3 sync + Tier-1 lookup
    endpoints (/tools/sync/stadium, /tools/sync/omnipong, their
    /events/{session_id} SSE routes, /tools/lookup/usatt). These endpoints
    drive a real browser through the relay, so they must never be reachable
    anonymously. Fails closed: if OPERATOR_TOKEN isn't configured, the
    endpoint refuses (503) rather than running open — no fallback to "no
    token configured = open"."""
    required = os.getenv("OPERATOR_TOKEN")
    if not required:
        raise HTTPException(
            status_code=503,
            detail="OPERATOR_TOKEN is not configured on the server — owner-gated endpoints refuse to run open.",
        )
    provided = request.headers.get("X-Operator-Token")
    if provided != required:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Operator-Token header.")

# Database connection
# Priority: env var (for Production/Render) > local sqlite file (Development)
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Fix for SQLAlchemy: Render uses 'postgres://' which is deprecated, replace with 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    # Local Development (SQLite)
    DB_URL = f"sqlite:///{os.path.abspath(os.path.join(os.path.dirname(__file__), '../../omnipong.db'))}"
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

# Create tables if they don't exist (Critical for fresh Render DB)
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@app.get("/")
def read_root():
    return {"status": "Rubberr Backend Running"}


@app.get("/demo")
def get_demo_profile():
    """Public read-only endpoint: returns the showcase player profile + recent stats.
    Safe to expose — no PII beyond what's already public on USATT.
    """
    session = SessionLocal()
    try:
        user_row = session.execute(
            text("SELECT name as full_name, current_rating as rating, usatt_id FROM users LIMIT 1")
        ).fetchone()

        stats_row = session.execute(
            text("""
                SELECT
                    COUNT(*) as total_matches,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses
                FROM matches
            """)
        ).fetchone()

        recent = session.execute(
            text("""
                SELECT opponent_name, result, date as match_date, score_summary, set_scores
                FROM matches
                ORDER BY date DESC
                LIMIT 10
            """)
        ).fetchall()

        return {
            "player": dict(user_row._mapping) if user_row else {},
            "stats": dict(stats_row._mapping) if stats_row else {},
            "recent_matches": [dict(r._mapping) for r in recent],
            "demo": True,
        }
    except Exception as e:
        return {"error": str(e), "demo": True}
    finally:
        session.close()


@app.get("/user")
def get_user():
    session = SessionLocal()
    try:
        # Fetch the main user (the configured player)
        result = session.execute(
            text(
                "SELECT name as full_name, current_rating as rating, usatt_id as usatt_number, phone_number FROM users LIMIT 1"
            )
        )
        user = result.fetchone()

        if user:
            return dict(user._mapping)

        # User requested NO auto-seeding. Strict DB state.
        raise HTTPException(
            status_code=404, detail="User not found in database. Run Sync."
        )

    except Exception as e:
        print(f"Error fetching user: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/matches")
def get_matches(source: str = None):
    session = SessionLocal()
    try:
        # Build Query
        query = "SELECT id, date, opponent_name, opponent_rating, score_summary, result, source, set_scores FROM matches"
        params = {}

        if source:
            query += " WHERE source = :source"
            params["source"] = source

        query += " ORDER BY date DESC"

        # Fetch detailed match history
        result = session.execute(text(query), params)

        matches = []
        for row in result:
            m = dict(row._mapping)

            # Default flags
            m["is_comeback"] = False
            m["is_choke"] = False
            m["is_close_game"] = False

            sets_str = m.get("set_scores")
            res_str = m.get("result")

            # Determine Win/Loss
            is_win = False
            if res_str == "Win":
                is_win = True
            elif res_str and "-" in res_str:
                try:
                    p1, p2 = map(int, res_str.split("-"))
                    if p1 > p2:
                        is_win = True
                except:
                    pass

            # Parse Sets for Patterns
            if sets_str:
                try:
                    # Clean and split "11-9, 9-11"
                    set_list = [s.strip() for s in sets_str.split(",")]
                    parsed_sets = []
                    has_close_set = False

                    for s in set_list:
                        if "-" in s:
                            try:
                                sp1, sp2 = map(int, s.split("-"))
                                parsed_sets.append((sp1, sp2))
                                if abs(sp1 - sp2) <= 2:
                                    has_close_set = True
                            except:
                                pass

                    m["is_close_game"] = has_close_set

                    if len(parsed_sets) > 0:
                        first_set = parsed_sets[0]
                        s1_user, s1_opp = first_set
                        won_first_set = s1_user > s1_opp

                        if not won_first_set and is_win:
                            m["is_comeback"] = True
                        elif won_first_set and not is_win:
                            m["is_choke"] = True

                except Exception:
                    m["is_win"] = is_win

            matches.append(m)

        return matches
    except Exception as e:
        print(f"Match fetch error: {e}")
        return []
    finally:
        session.close()


@app.delete("/matches/{match_id}")
def delete_match(match_id: int):
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM matches WHERE id = :id"), {"id": match_id})
        session.commit()
        return {"status": "success", "message": "Match deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/tournaments/signup")
async def signup_tournament(
    tournament_title: str, recommended_events: list[str] = None
):
    try:
        from omnipong_scraper import OmniPongScraper, AsyncSessionLocal

        scraper = OmniPongScraper(browser_manager)

        # If no events provided, we proceed with None so scraper uses Smart Matching
        # Logic: If frontend sends [], scraper will self-determine based on rating

        # if not recommended_events:
        #     # Try to fetch recommendations if missing
        #      intel = get_tournament_intelligence(tournament_title)
        #      if intel and intel.get("recommendations"):
        #          recommended_events = intel["recommendations"][0].get("recommended_events", [])

        # We don't raise error anymore if empty
        # if not recommended_events:
        #     raise HTTPException(status_code=400, detail="No recommended events found or provided.")

        result = await scraper.signup_for_tournament(
            tournament_title, recommended_events
        )

        if result.get("status") == "success":
            # Update DB status to 'Entered'
            from models import Activity
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                stmt = select(Activity).where(Activity.title == tournament_title)
                res = await session.execute(stmt)
                activity = res.scalar_one_or_none()

                if activity:
                    activity.status = "Entered"
                    # Also optionally update specific events if we want granular tracking
                    await session.commit()
                    print(f"Updated Activity '{tournament_title}' status to 'Entered'")

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tournaments")
def get_tournaments(region: str = "local"):
    session = SessionLocal()
    try:
        # Fetch active tournaments
        result = session.execute(
            text(
                "SELECT title, location, date_range, status, flyer_url FROM activities WHERE activity_type='tournament' ORDER BY id DESC"
            )
        )

        # known TX cities for filtering
        tx_cities = [
            "plano",
            "austin",
            "houston",
            "san antonio",
            "dallas",
            "richardson",
            "irving",
            "katy",
            "allen",
            "colleyville",
            "round rock",
            "fort worth",
            "lubbock",
            "el paso",
            "arlington",
        ]

        tournaments = []
        for row in result:
            d = dict(row._mapping)

            # Basic Location Check
            loc_lower = (d["location"] or "").lower()
            is_tx = any(city in loc_lower for city in tx_cities)

            # Filtering Logic
            if region == "local" and not is_tx:
                continue

            # Real Data Only - No Mocks
            # If we have real events/cost in DB later, fetch here. For now leave empty/null.
            d["estimated_cost"] = None
            d["events"] = None
            d["tier"] = None

            tournaments.append(d)

        return tournaments
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/notifications")
def get_notifications():
    session = SessionLocal()
    try:
        # Fetch unread notifications
        result = session.execute(
            text(
                "SELECT id, type, content, is_read, created_at FROM notifications WHERE is_read = 0 ORDER BY created_at DESC"
            )
        )
        notifications = []
        for row in result:
            d = dict(row._mapping)
            import json

            try:
                d["content"] = json.loads(d["content"])
            except:
                pass
            notifications.append(d)
        return notifications
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int):
    session = SessionLocal()
    try:
        session.execute(
            text("UPDATE notifications SET is_read = 1 WHERE id = :id"), {"id": notif_id}
        )
        session.commit()
        return {"status": "success"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/tools/check-tournaments")
async def check_tournaments():
    try:
        script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../daily_check.py")
        )
        code, stdout, stderr = await run_script_managed(script_path)

        if code == 0:
            return {"status": "success", "log": stdout.decode()}
        else:
            return {"status": "error", "log": stderr.decode()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/omnipong")
async def sync_omnipong():
    try:
        # Trigger OmniPong Autoscrape
        script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../autoscrape.py")
        )
        code, stdout, stderr = await run_script_managed(script_path)

        if code == 0:
            return {"status": "success", "log": stdout.decode()}
        else:
            return {"status": "error", "log": stderr.decode()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("shutdown")
async def shutdown_event():
    print("Shutting down backend...")
    # 1. Stop BrowserManager
    try:
        await browser_manager.stop()
        print("BrowserManager stopped.")
    except Exception as e:
        print(f"Error stopping BrowserManager: {e}")

    # 2. Terminate all tracked subprocesses
    for process in active_processes:
        try:
            if process.returncode is None:
                print(f"Terminating background process {process.pid}")
                process.terminate()
                await process.wait()
        except Exception as e:
            print(f"Error terminating process {process.pid}: {e}")


@app.post("/tools/sync/stadium")
async def tool_sync_stadium(req: StadiumSyncStartRequest, request: Request):
    """Tier-3: pull the user's OWN Stadium (stadiumcompete.com) match history
    through their own already-logged-in browser via the relay — no stored
    credentials, ever (RELAY_ARCHITECTURE.md §2/§5). The user logs into Stadium
    themselves in their own Chrome; this only drives that tab.

    Matches StadiumSyncPanel.tsx's contract: starts the run in the
    background and returns {"session_id": ...} immediately; gate prompts and
    the final result stream over GET /tools/sync/stadium/events (Phase 2
    seam #1). Private per-user data is handed straight to the frontend for
    the user's own IndexedDB ledger — it is NOT written to the server DB
    (build plan: "private per-user scraped data lives in the user's browser").
    """
    _require_operator_token(request)
    return await _start_tier3_sync(
        task=(
            "Open the Stadium (stadiumcompete.com) matches/dashboard for the "
            "already logged-in user and extract their match history: for each "
            "match, the opponent name, date, result, score summary, and set "
            "scores."
        ),
        site="stadium",
        player_name=req.player_name or PLAYER_FULL_NAME,
        model=req.model,
        request=request,
    )


@app.get("/tools/sync/stadium/events/{session_id}")
async def tool_sync_stadium_events(session_id: str, request: Request) -> StreamingResponse:
    """SSE push channel for the sync started by POST /tools/sync/stadium.
    Event names/payloads match StadiumSyncPanel.tsx exactly: gate_open,
    gate_cleared, gate_timeout, done (BrowserTaskResult).

    S5: session_id (the relay session_token) is a path segment, not a query
    string param — query strings land in proxy/access logs and browser
    history, against RELAY_ARCHITECTURE.md §5's own rule."""
    _require_operator_token(request)
    return _sse_response_for_sync_session(session_id)


@app.post("/tools/sync/omnipong")
async def tool_sync_omnipong_personal(req: StadiumSyncStartRequest, request: Request):
    """Tier-3: pull the user's OWN OmniPong match/tournament history through
    their own already-logged-in browser via the relay. Same no-stored-creds,
    background+SSE contract as /tools/sync/stadium — distinct from
    /sync/omnipong, which refreshes the Tier-2 public feed under the owner's
    own login."""
    _require_operator_token(request)
    return await _start_tier3_sync(
        task=(
            "Open the OmniPong (omnipong.com) 'My Matches' / tournament history "
            "page for the already logged-in user and extract match results and "
            "tournament entries."
        ),
        site="omnipong",
        player_name=req.player_name or PLAYER_FULL_NAME,
        model=req.model,
        request=request,
    )


@app.get("/tools/sync/omnipong/events/{session_id}")
async def tool_sync_omnipong_events(session_id: str, request: Request) -> StreamingResponse:
    """SSE push channel for the sync started by POST /tools/sync/omnipong.
    S5: session_id in the path, not the query string — see
    tool_sync_stadium_events's docstring."""
    _require_operator_token(request)
    return _sse_response_for_sync_session(session_id)


@app.get("/tools/lookup/usatt")
async def tool_lookup_usatt(name: str, request: Request, session_token: str | None = None):
    """Tier-1: public name -> USATT rating/tournament history lookup, no login.

    USATT (usatt.simplycompete.com) is Cloudflare-walled against plain
    requests/fetch (confirmed during Phase-0 spec research), so this cannot be
    a server-side HTTP call — it must go through a REAL browser. Per the build
    plan's Tier-1 row ("real browser via relay"), this reuses the same
    browser-agent/relay path as Tier-3, but against a shared "public" companion
    session that requires no personal login, rather than a per-visitor one.

    Method + response shape match the frontend's contract exactly
    (rubberr/frontend/src/app/lookup/page.tsx) — Phase 2 seam #3 resolved by
    switching this endpoint from POST to GET (E's side) and reshaping the
    response from the generic BrowserTaskResult.matches[] into
    {status, player, rating_history, tournaments} (browser_agent.py's
    site == "usatt" branch returns matches == [profile_dict] for exactly
    this purpose, see extract_usatt_profile).

    The shared public companion session is provisioned here (Phase 2 seam
    #4) by calling relay POST /session/start with RELAY_PUBLIC_REGISTER_TOKEN
    — the register token of an always-on companion+browser running on Y6
    (see docs/PLATFORM_RUNBOOK.md). Callers may instead pass their own
    session_token if they already have a live companion. If neither is
    available this fails loudly with a clean 503 — no mocked/fake data is
    ever returned.
    """
    _require_operator_token(request)
    # S2: reject a bad `name` before minting a relay session for it.
    if BROWSER_AGENT_AVAILABLE:
        name_error = validate_player_name(name)
        if name_error:
            raise HTTPException(status_code=400, detail=f"Invalid name: {name_error}")

    relay_base_url = os.getenv("RELAY_BASE_URL")
    if not relay_base_url:
        raise HTTPException(status_code=500, detail="RELAY_BASE_URL is not configured on the server.")

    if session_token is None:
        public_register_token = os.getenv("RELAY_PUBLIC_REGISTER_TOKEN")
        if not public_register_token:
            raise HTTPException(
                status_code=503,
                detail="No public relay companion configured (RELAY_PUBLIC_REGISTER_TOKEN unset).",
            )
        session_token = await _provision_relay_session(public_register_token, relay_base_url=relay_base_url)

    result = await _run_browser_agent_task(
        task=f"Look up USATT rating/history/tournaments for '{name}'.",
        site="usatt",
        player_name=name,
        session_token=session_token,
        model=None,
        request=request,
    )
    await _stop_relay_session(session_token, relay_base_url=relay_base_url)  # E3

    if result.status != "ok":
        return _browser_task_error(result)

    profile = result.matches[0] if result.matches else {"not_found": True, "player": None, "rating_history": [], "tournaments": []}
    if profile.get("not_found") or not profile.get("player"):
        return {"status": "not_found", "message": f'No USATT record found for "{name}"'}

    return {
        "status": "success",
        "player": profile["player"],
        "rating_history": profile.get("rating_history") or [],
        "tournaments": profile.get("tournaments") or [],
    }


@app.get("/tools/context")
def get_agent_context():
    session = SessionLocal()
    try:
        # 1. User Profile
        user_res = session.execute(
            text(
                "SELECT name as full_name, current_rating as rating, usatt_id as usatt_number FROM users LIMIT 1"
            )
        ).fetchone()
        user_data = dict(user_res._mapping) if user_res else {}

        # 2. Recent Matches (Last 5)
        matches_res = session.execute(
            text(
                "SELECT date, opponent_name, opponent_rating, result, score_summary, set_scores FROM matches ORDER BY date DESC LIMIT 5"
            )
        )
        recent_matches = [dict(row._mapping) for row in matches_res]

        # 3. Upcoming Tournaments (Next 3)
        tourney_res = session.execute(
            text(
                "SELECT title, location, date_range, status FROM activities WHERE activity_type='tournament' ORDER BY id DESC LIMIT 3"
            )
        )
        upcoming_tournaments = [dict(row._mapping) for row in tourney_res]

        return {
            "user": user_data,
            "recent_matches": recent_matches,
            "upcoming_tournaments": upcoming_tournaments,
            "system_note": "Use this data to answer the user's questions about their table tennis career.",
        }
    except Exception as e:
        print(f"Tool Context Error: {e}")
        return {"error": str(e)}
    finally:
        session.close()


@app.get("/stats")
def get_stats(source: str = "omnipong"):
    """Calculate live stats based on match history for a specific source"""
    session = SessionLocal()
    try:
        # Base query for the source
        # Note: source='omnipong' for USATT, 'stadium_league'/'stadium' for Club League
        # Note: source='omnipong' for USATT, 'stadium_league'/'stadium' for Club League, 'arcade' for Arcade Mode
        if source == "usatt":
            source_filter = "source = 'omnipong'"
        elif source == "arcade":
            source_filter = "source = 'arcade'"
        else:
            source_filter = "source IN ('stadium', 'stadium_league')"

        # 1. Fetch all matches with relevant fields
        query = text(f"SELECT result, set_scores FROM matches WHERE {source_filter}")
        matches = session.execute(query, {"source": source}).fetchall()

        total = len(matches)
        wins = 0
        losses = 0

        # Pattern Tracking
        close_sets_swung = 0
        close_sets_won = 0
        comebacks = 0  # Lost Set 1 -> Won Match
        chokes = 0  # Won Set 1 -> Lost Match

        for m in matches:
            res_str = m[0]
            sets_str = m[1]

            # Determine Match Result
            is_win = False
            if res_str == "Win":
                is_win = True
            elif res_str and "-" in res_str:
                try:
                    p1, p2 = map(int, res_str.split("-"))
                    if p1 > p2:
                        is_win = True
                except:
                    pass

            if is_win:
                wins += 1
            else:
                losses += 1

            # Parse Set Scores for Patterns
            if sets_str:
                try:
                    # Split "11-9, 9-11" -> ["11-9", "9-11"]
                    set_list = [s.strip() for s in sets_str.split(",")]
                    parsed_sets = []
                    for s in set_list:
                        if "-" in s:
                            sp1, sp2 = map(int, s.split("-"))
                            parsed_sets.append((sp1, sp2))

                            # Close Game Analysis (diff <= 2)
                            if abs(sp1 - sp2) <= 2:
                                close_sets_swung += 1
                                if sp1 > sp2:
                                    close_sets_won += 1

                    # Pattern: Comeback / Choke
                    if len(parsed_sets) > 0:
                        first_set = parsed_sets[0]
                        # Assuming left number is User (scraped logic puts User score first usually?
                        # Wait, scraper logic `p1Score = scoreMain[0]` -> `mainScore = p1-p2`.
                        # In scraper, p1 is usually the "MatchCard-score" which is dynamic based on user side?
                        # Actually in scraper: `validSets.push(`${s1}-${s2}`);` where s1 is first div.
                        # Usually the "User" score is on the left if scraping logic is consistent.
                        # Let's assume Left = User for now as Scraper tries to orient.

                        s1_user, s1_opp = first_set
                        won_first_set = s1_user > s1_opp

                        if not won_first_set and is_win:
                            comebacks += 1
                        elif won_first_set and not is_win:
                            chokes += 1

                except Exception as ex:
                    # print(f"Error parsing sets: {ex}")
                    pass

        win_rate = round((wins / total * 100)) if total > 0 else 0

        # 2. Tournaments (Distinct Days)
        tourney_query = text(
            f"SELECT COUNT(DISTINCT date) FROM matches WHERE {source_filter}"
        )
        tourneys = session.execute(tourney_query, {"source": source}).scalar() or 0

        # 3. Rating Trend (Placeholder)
        trend = "+15"

        return {
            "win_rate": f"{win_rate}%",
            "wins": wins,
            "losses": losses,
            "tournaments": str(tourneys),
            "trend": trend,
            "rating_context": "USATT Official"
            if source == "usatt"
            else ("Arcade Mode" if source == "arcade" else "Club League"),
            "patterns": {
                "comebacks": comebacks,
                "chokes": chokes,
                "close_game_win_rate": round(close_sets_won / close_sets_swung * 100)
                if close_sets_swung > 0
                else 0,
            },
        }
    except Exception as e:
        print(f"Stats Error: {e}")
        return {"error": str(e)}
    finally:
        session.close()


@app.get("/rating_history")
def get_rating_history(source: str = "omnipong"):
    """Fetch user's rating progression over time"""
    session = SessionLocal()
    try:
        # Match source filtering logic with other endpoints
        if source == "usatt":
            source_filter = "source = 'omnipong'"
        elif source == "arcade":
            source_filter = "source = 'arcade'"
        else:
            source_filter = "source IN ('stadium', 'stadium_league')"

        query = text(f"""
            SELECT date, rating, notes 
            FROM rating_history 
            WHERE {source_filter}
            ORDER BY date ASC
        """)

        result = session.execute(query)
        history = [dict(row._mapping) for row in result]
        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/tools/sync/league")
async def tool_sync_league():
    """Trigger Stadium league scraper to fetch match history from league pages"""
    try:
        script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "stadium_league_scraper.py")
        )
        code, stdout, stderr = await run_script_managed(script_path)

        if code == 0:
            return {
                "status": "success",
                "message": "League match history synced successfully",
                "output": stdout.decode(),
            }
        else:
            return {"status": "error", "message": f"Sync failed: {stderr.decode()}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/tools/sync/league_players")
async def tool_sync_league_players():
    """Trigger OmniPong search for all league players to sync USATT IDs and ratings"""
    try:
        # Use the absolute path to the sync script
        script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../sync_omnipong_players.py")
        )
        code, stdout, stderr = await run_script_managed(script_path)

        if code == 0:
            return {
                "status": "success",
                "message": "League players synced successfully",
                "output": stdout.decode(),
            }
        else:
            return {"status": "error", "message": f"Sync failed: {stderr.decode()}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/tools/sync/tournaments")
async def tool_sync_tournaments(scope: str = "regional"):
    """
    Trigger OmniPong tournament sync.
    scopes: 'history' (my history), 'regional' (Region 8), 'all'
    """
    print(f"\n{'=' * 60}")
    print(f"🎾 [BACKEND] Tournament sync endpoint called")
    print(f"🎾 [BACKEND] Scope parameter: {scope}")
    print(f"{'=' * 60}\n")

    try:
        script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../sync_tournaments.py")
        )
        print(f"🎾 [BACKEND] Script path: {script_path}")
        print(f"🎾 [BACKEND] Script exists: {os.path.exists(script_path)}")
        print(
            f"🎾 [BACKEND] Calling run_script_managed with args: ['--scope', '{scope}']"
        )

        code, stdout, stderr = await run_script_managed(script_path, ["--scope", scope])

        print(f"🎾 [BACKEND] Script exit code: {code}")
        print(f"🎾 [BACKEND] Script stdout length: {len(stdout)} bytes")
        print(f"🎾 [BACKEND] Script stderr length: {len(stderr)} bytes")
        print(f"🎾 [BACKEND] Script stdout:\n{stdout.decode()}")
        if stderr:
            print(f"🎾 [BACKEND] Script stderr:\n{stderr.decode()}")

        if code == 0:
            print(f"🎾 [BACKEND] Returning SUCCESS response")
            return {
                "status": "success",
                "message": f"Tournament sync ({scope}) complete",
                "output": stdout.decode(),
            }
        else:
            print(f"🎾 [BACKEND] Returning ERROR response")
            return {"status": "error", "message": f"Sync failed: {stderr.decode()}"}
    except Exception as e:
        print(f"🎾 [BACKEND] Exception caught: {type(e).__name__}: {str(e)}")
        import traceback

        print(f"🎾 [BACKEND] Traceback:\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


@app.post("/tools/query/matches")
def tool_query_matches(
    opponent_name: str = None, date_from: str = None, result: str = None
):
    session = SessionLocal()
    try:
        query_str = "SELECT date, opponent_name, result, score_summary, set_scores FROM matches WHERE 1=1"
        params = {}

        if opponent_name:
            query_str += " AND opponent_name LIKE :opp"
            params["opp"] = f"%{opponent_name}%"
        if date_from:
            query_str += " AND date >= :dt"
            params["dt"] = date_from
        if result:
            query_str += " AND result = :res"
            params["res"] = result

        query_str += " ORDER BY date DESC LIMIT 10"

        res = session.execute(text(query_str), params)
        matches = [dict(row._mapping) for row in res]
        return matches
    except Exception as e:
        return {"error": str(e)}
    finally:
        session.close()


@app.post("/tools/stats/calculate")
def tool_stats_calculate(metric: str = "win_rate"):
    # Reuse get_stats logic but flexible
    return get_stats(source="omnipong")  # Default


@app.post("/tools/query/tournaments")
def tool_query_tournaments(location: str = None):
    session = SessionLocal()
    try:
        query_str = "SELECT title, location, date_range, status FROM activities WHERE activity_type='tournament'"
        params = {}
        if location:
            query_str += " AND location LIKE :loc"
            params["loc"] = f"%{location}%"

        res = session.execute(text(query_str), params)
        return [dict(row._mapping) for row in res]
    except Exception as e:
        return {"error": str(e)}
    finally:
        session.close()


@app.post("/tools/search/players")
def tool_search_players(req: PlayerSearch):
    """Search for a player in our local database (USATT ID, Rating, State)"""
    session = SessionLocal()
    try:
        name = req.name
        query_str = "SELECT name, usatt_id, rating, state FROM players WHERE 1=1"
        params = {}
        if name:
            query_str += " AND (name LIKE :name OR usatt_id = :exact_id)"
            params["name"] = f"%{name}%"
            params["exact_id"] = name

        res = session.execute(text(query_str), params)
        players = [dict(row._mapping) for row in res]

        # If not found in players table, check matches table for opponent_name
        if not players and name:
            match_res = session.execute(
                text(
                    "SELECT DISTINCT opponent_name as name, opponent_usatt_id as usatt_id, opponent_rating as rating FROM matches WHERE opponent_name LIKE :name AND opponent_rating IS NOT NULL"
                ),
                {"name": f"%{name}%"},
            )
            players = [dict(row._mapping) for row in match_res]

        if not players:
            return {
                "status": "not_found",
                "message": f"No player found locally matching '{name}'",
            }

        return {"status": "success", "players": players}
    except Exception as e:
        return {"error": str(e)}
    finally:
        session.close()


# --- HELPER: Save Match Logic ---
def save_arcade_match(
    session, opponent_name, result, score_summary, set_scores, date_obj=None
):
    from models import Match, Player
    from datetime import datetime

    # 1. Find/Create Opponent
    opp_rating = 1200
    existing_opp = session.execute(
        text("SELECT rating FROM players WHERE name = :n"), {"n": opponent_name}
    ).fetchone()
    if existing_opp and existing_opp.rating:
        opp_rating = existing_opp.rating

    # 2. Create Match
    new_match = Match(
        date=date_obj if date_obj else datetime.now().date(),
        opponent_name=opponent_name,
        opponent_rating=opp_rating,
        result=result,
        score_summary=score_summary,
        set_scores=set_scores,
        source="arcade",
        activity_id=None,
    )
    session.add(new_match)
    session.commit()
    return new_match


# --- MULTI-MODAL & AI HANDLERS ---
from .ai_handler import transcribe_audio, parse_match_intent
from fastapi import File, UploadFile, Form, Request, Response
import shutil
import os


@app.post("/arcade/transcribe")
async def arcade_transcribe(file: UploadFile = File(...)):
    """
    Accepts an audio file, transcribes it, and parses match intent using LLM.
    """
    temp_filename = f"temp_{file.filename}"
    try:
        # Save temp file
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Transcribe
        transcript = await transcribe_audio(temp_filename)

        # Parse
        parsed = await parse_match_intent(transcript)

        return {
            "status": "success",
            "transcript": transcript,
            "intent": parsed.get("intent"),
            "confirmation": parsed.get("confirmation_message"),
            "missing": parsed.get("missing_info"),
        }
    except Exception as e:
        print(f"❌ Transcribe Error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "transcript": "Error during processing",
            "intent": {},
        }
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)


@app.post("/arcade/process")
async def arcade_process(req: ProcessText):
    """
    Accepts raw text (e.g. from local iOS Speech-to-Text), and parses match intent.
    """
    try:
        # Parse text directly
        parsed = await parse_match_intent(req.text)

        return {
            "status": "success",
            "transcript": req.text,
            "intent": parsed.get("intent"),
            "confirmation": parsed.get("confirmation_message"),
            "missing": parsed.get("missing_info"),
        }
    except Exception as e:
        print(f"❌ Process Error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "transcript": req.text,
            "intent": {},
        }


@app.post("/webhooks/twilio")
async def twilio_webhook(request: Request):
    """
    Handles incoming SMS/Voice from Twilio.
    ROUTES based on intent classification: Match Report vs General Query.
    """
    form_data = await request.form()
    body = form_data.get("Body", "")  # SMS Text

    if body:
        try:
            # 1. AI Parse & Classify
            parsed = await parse_match_intent(body)
            intent = parsed.get("intent")  # Now contains message_type

            # 2. ROUTING LOGIC
            message_type = intent.get("message_type", "query")

            if message_type == "match_report":
                # --- MATCH REPORT FLOW ---
                # Support both old (opponent_name/user_score) and new (player1_name/player2_name) formats
                p1_score = intent.get("player1_score") or intent.get("user_score")
                p2_score = intent.get("player2_score") or intent.get("opponent_score")
                opponent_name = intent.get("player2_name") or intent.get(
                    "opponent_name"
                )

                if opponent_name and p1_score is not None:
                    session = SessionLocal()
                    try:
                        result = "Win" if p1_score > p2_score else "Loss"
                        score_summary = f"{p1_score}-{p2_score}"
                        set_scores = intent.get("set_scores", "")

                        save_arcade_match(
                            session, opponent_name, result, score_summary, set_scores
                        )

                        xml_content = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>Match Saved! {parsed["confirmation_message"]}</Message></Response>'
                        return Response(
                            content=xml_content, media_type="application/xml"
                        )
                    except Exception as e:
                        print(f"Twilio Save Error: {e}")
                        xml_error = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>Error saving match: {str(e)}</Message></Response>'
                        return Response(content=xml_error, media_type="application/xml")
                    finally:
                        session.close()
                else:
                    # Match report but missing info
                    xml_missing = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{parsed.get("confirmation_message", "I need more details to save the match.")}</Message></Response>'
                    return Response(content=xml_missing, media_type="application/xml")

            else:
                # --- GENERAL QUERY FLOW (Hand off to Claude) ---
                # "Is Steve better than me?" -> "message_type": "query"
                print(f"Routing to Claude: {body}")
                claude_reply = await get_claude_response(body)

                # Twilio SMS max length is 1600 chars, usually splits. Claude can be verbose.
                # Just send it.
                xml_reply = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{claude_reply}</Message></Response>'
                return Response(content=xml_reply, media_type="application/xml")

        except Exception as e:
            xml_fail = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>I\'m having trouble understanding. Error: {str(e)}</Message></Response>'
            return Response(content=xml_fail, media_type="application/xml")

    return Response(content="OK", media_type="text/plain")


# --- ARCADE MODE ENDPOINTS ---


class ArcadeScoreSubmission(BaseModel):
    transcript: str = None
    manual_score: str = None
    # Support both old and new field names
    opponent_name: str = None  # Old field (for backward compatibility)
    player1_name: str = None  # New field
    player2_name: str = None  # New field
    date: str = None  # YYYY-MM-DD


@app.post("/arcade/lookup_player")
def arcade_lookup_player(req: PlayerSearch):
    """
    Find or Create a local player for Arcade Mode.
    If player exists (by name), return info.
    If not, return basic info (can default to 1200 or estimate).
    """
    session = SessionLocal()
    try:
        name = req.name
        if not name:
            return {"status": "error", "message": "Name is required"}

        # Case insensitive search
        player = session.execute(
            text("SELECT * FROM players WHERE name LIKE :name"), {"name": name}
        ).fetchone()

        if player:
            return {"status": "found", "player": dict(player._mapping)}
        else:
            return {"status": "not_found", "message": "Player not found in database."}
    except Exception as e:
        return {"error": str(e)}
    finally:
        session.close()


@app.post("/arcade/submit_score")
async def arcade_submit_score(data: ArcadeScoreSubmission):
    """
    Parse and submit a score for Arcade Mode.
    Handles natural language input like 'I won 3-0' or '11-9, 11-8...'.
    Uses the same AI logic as the SMS agent for high accuracy.
    """
    session = SessionLocal()
    try:
        from datetime import date

        # 1. Smarter AI Parsing
        # Use the same logic as the Twilio agent if transcript is provided
        raw_input = data.transcript or data.manual_score or ""

        result = "Win"
        score_summary = data.manual_score or "3-0"
        set_scores = ""
        confirmation = ""

        if raw_input:
            try:
                parsed = await parse_match_intent(raw_input)
                intent = parsed.get("intent", {})

                # Extract values from AI parsing (support both old and new field names)
                u_score = intent.get("player1_score") or intent.get("user_score")
                o_score = intent.get("player2_score") or intent.get("opponent_score")
                if u_score is not None and o_score is not None:
                    result = "Win" if u_score > o_score else "Loss"
                    score_summary = f"{u_score}-{o_score}"
                    set_scores = intent.get("set_scores", "")
                    confirmation = parsed.get("confirmation_message", "")
            except Exception as ai_err:
                print(f"AI Parse Error: {ai_err}")
                return {
                    "status": "error",
                    "message": f"AI Parsing failed: {str(ai_err)}",
                }

        # 2. Save Match to DB
        from models import Match, Player

        # Support both old and new field names - fully dynamic, no hardcoded names
        user_name = data.player1_name or "User"  # Default to generic if not provided
        opp_name = (
            data.player2_name or data.opponent_name
        )  # Prefer new field, fallback to old

        if not opp_name:
            return {"status": "error", "message": "Missing opponent/player2 name"}

        # If only opponent provided (legacy), infer user_name from AI intent if available
        if user_name == "User" and raw_input:
            if intent.get("player1_name"):
                user_name = intent["player1_name"]

        opp_rating = 1200  # Default

        # Try to find existing rating
        existing_opp = session.execute(
            text("SELECT rating FROM players WHERE name = :n"), {"n": opp_name}
        ).fetchone()
        if existing_opp and existing_opp.rating:
            opp_rating = existing_opp.rating

        # Handle Date/Time (Support full ISO or simple date)
        match_dt = datetime.now()
        if data.date:
            try:
                # Try full ISO8601 first
                match_dt = datetime.fromisoformat(data.date.replace("Z", "+00:00"))
            except ValueError:
                try:
                    # Fallback to simple date
                    match_dt = datetime.strptime(data.date, "%Y-%m-%d")
                except:
                    pass

        # Determine Winner/Loser names for the record
        winner_name = user_name if result == "Win" else opp_name
        loser_name = opp_name if result == "Win" else user_name

        new_match = Match(
            date=match_dt,
            opponent_name=opp_name,
            opponent_rating=opp_rating,
            winner_name=winner_name,
            loser_name=loser_name,
            result=result,
            score_summary=score_summary,  # Overall "3-1"
            set_scores=set_scores,  # Detailed "11-9, 9-11"
            source="arcade",
            activity_id=None,  # Not linked to a tournament/league
        )

        session.add(new_match)
        session.commit()

        return {
            "status": "success",
            "match_id": new_match.id,
            "summary": f"Recorded {result} vs {opp_name} ({score_summary})",
            "confirmation": confirmation,
        }

    except Exception as e:
        session.rollback()
        print(f"Arcade Submit Error: {e}")
        return {"error": str(e)}
    finally:
        session.close()


def get_practice_partners(limit: int = 5):
    """
    Analyze match history to recommend optimal practice partners.
    Considers: skill level match, competitiveness, frequency of play, and improvement potential.
    """
    session = SessionLocal()
    try:
        # Get all matches with opponent data
        query = text("""
            SELECT
                opponent_name,
                opponent_rating,
                result,
                set_scores,
                date,
                score_summary
            FROM matches
            WHERE opponent_name IS NOT NULL
            ORDER BY date DESC
        """)

        result = session.execute(query)
        matches = [dict(row._mapping) for row in result]

        # Get user's current rating (approximate from recent matches)
        user_rating_query = text("""
            SELECT current_rating FROM users LIMIT 1
        """)
        user_rating_result = session.execute(user_rating_query).scalar()
        user_rating = user_rating_result or 1500  # Default if not found

        # Analyze opponents
        opponent_stats = {}

        for match in matches:
            opp_name = match["opponent_name"]
            if not opp_name:
                continue

            if opp_name not in opponent_stats:
                opponent_stats[opp_name] = {
                    "name": opp_name,
                    "rating": match["opponent_rating"],
                    "matches_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "close_matches": 0,
                    "last_played": match["date"],
                    "recent_trend": [],  # Track recent results
                }

            stats = opponent_stats[opp_name]
            stats["matches_played"] += 1

            # Track wins/losses
            if match["result"] in ["W", "Win"]:
                stats["wins"] += 1
                stats["recent_trend"].append("W")
            else:
                stats["losses"] += 1
                stats["recent_trend"].append("L")

            # Detect close matches
            set_scores = match.get("set_scores", "")
            if set_scores:
                try:
                    sets = set_scores.split(",")
                    for s in sets:
                        s = s.strip()
                        if "-" in s:
                            s1, s2 = map(int, s.split("-"))
                            if abs(s1 - s2) <= 2:  # Close set
                                stats["close_matches"] += 1
                                break
                except:
                    pass

        # Score each opponent for practice value
        recommendations = []

        for opp_name, stats in opponent_stats.items():
            if stats["matches_played"] < 1:
                continue

            score = 0
            reasons = []

            # 1. Skill Level Match (higher score for similar rating ±150)
            rating_diff = abs((stats["rating"] or user_rating) - user_rating)
            if rating_diff <= 50:
                score += 30
                reasons.append("Similar skill level (perfect practice match)")
            elif rating_diff <= 150:
                score += 20
                reasons.append("Good skill level match")
            elif stats["rating"] and stats["rating"] > user_rating:
                score += 15
                reasons.append("Higher rated (challenging practice)")

            # 2. Competitiveness (close matches are valuable)
            close_match_rate = stats["close_matches"] / stats["matches_played"]
            if close_match_rate >= 0.5:
                score += 25
                reasons.append("Very competitive matches (high learning potential)")
            elif close_match_rate > 0:
                score += 15
                reasons.append("Competitive matches")

            # 3. Win Rate (ideal is 40-60% for growth)
            win_rate = stats["wins"] / stats["matches_played"]
            if 0.4 <= win_rate <= 0.6:
                score += 25
                reasons.append("Balanced win/loss record (optimal for improvement)")
            elif 0.3 <= win_rate < 0.4:
                score += 15
                reasons.append("Challenging opponent (room to improve)")
            elif win_rate < 0.3:
                score += 10
                reasons.append("Tough opponent (valuable for growth)")

            # 4. Frequency (regular practice partners are valuable)
            if stats["matches_played"] >= 5:
                score += 15
                reasons.append("Regular practice partner")
            elif stats["matches_played"] >= 3:
                score += 10
                reasons.append("Familiar opponent")

            # 5. Recent Activity (prefer players you can still practice with)
            try:
                from datetime import datetime, timedelta

                last_played = datetime.strptime(str(stats["last_played"]), "%Y-%m-%d")
                days_since = (datetime.now() - last_played).days
                if days_since <= 30:
                    score += 10
                    reasons.append("Recently played")
                elif days_since <= 90:
                    score += 5
            except:
                pass

            # --- Normalize Scores for Frontend (0.0 to 1.0) ---

            # 1. Skill Match Score (1.0 if within 50pts, decay linearly to 0 at 400pts diff)
            skill_score = max(0, 1 - (rating_diff / 400))
            if rating_diff <= 50:
                skill_score = 1.0

            # 2. Competitiveness Score (Percent of close matches)
            comp_score = min(
                1.0, close_match_rate * 1.5
            )  # Boost it a bit so 33% close is 0.5 score

            # 3. Win Rate Balance (Bell curve peaking at 0.5)
            # Optimal is 0.5. Distance from 0.5: abs(win_rate - 0.5). Max dist is 0.5.
            # Score = 1 - (dist * 2) -> If 0.5, dist 0, score 1. If 1.0 or 0.0, dist 0.5, score 0.
            balance_score = 1.0 - (abs(win_rate - 0.5) * 2)

            # 4. Recent Activity Score
            recent_score = 0.0
            try:
                from datetime import datetime

                last_played = datetime.strptime(str(stats["last_played"]), "%Y-%m-%d")
                days_since = (datetime.now() - last_played).days
                recent_score = max(0, 1 - (days_since / 90))  # Decay over 3 months
            except:
                pass

            # Aggregate Total Score (Weighted Average)
            total_weighted_score = (
                (skill_score * 0.3)
                + (comp_score * 0.3)
                + (balance_score * 0.3)
                + (recent_score * 0.1)
            )

            recommendations.append(
                {
                    "player_name": opp_name,
                    "rating": stats["rating"],
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "match_count": stats["matches_played"],
                    "total_score": round(total_weighted_score, 2),
                    "reason": reasons[0] if reasons else "Good practice partner",
                    "last_played": str(stats["last_played"]),
                    "scores": {
                        "skill_match": round(skill_score, 2),
                        "competitiveness": round(comp_score, 2),
                        "win_rate_balance": round(balance_score, 2),
                        "recent_activity": round(recent_score, 2),
                    },
                }
            )

        # Sort by score and return top recommendations
        recommendations.sort(key=lambda x: x["total_score"], reverse=True)

        return {
            "user_rating": user_rating,
            "recommendations": recommendations[:limit],
            "total_opponents": len(opponent_stats),
            "analysis": f"Analyzed {len(matches)} matches against {len(opponent_stats)} different opponents",
        }

    except Exception as e:
        return {"error": str(e)}
    finally:
        session.close()


# Removed definition of get_tournament_intelligence here as it is now imported.


@app.get("/tools/stats")
def get_tool_stats():
    """Tool-specific endpoint for stats summary"""
    return get_stats(source="omnipong")


@app.get("/tools/analysis")
def get_tool_analysis():
    """Tool-specific endpoint for match analysis context"""
    session = SessionLocal()
    try:
        # Fetch some analysis patterns (comebacks, chokes)
        stats = get_stats(source="omnipong")
        # Fetch some recent close matches
        result = session.execute(
            text(
                "SELECT date, opponent_name, result, set_scores FROM matches WHERE set_scores LIKE '%11-9%' OR set_scores LIKE '%9-11%' LIMIT 3"
            )
        )
        close_matches = [dict(row._mapping) for row in result]

        return {
            "summary": stats,
            "notable_matches": close_matches,
            "instruction": "Explain these patterns to the user. For example, if they have many chokes, suggest focus on late-game composure.",
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        session.close()


@app.get("/tools/practice_partners")
def get_tool_practice_partners(limit: int = 5):
    """Tool-specific endpoint for practice partner recommendations"""
    return get_practice_partners(limit=limit)


@app.get("/tools/tournament_intelligence")
def get_tool_tournament_intelligence(tournament_title: str = None, limit: int = 5):
    """Tool-specific endpoint for AI-enhanced tournament recommendations"""
    return get_tournament_intelligence(tournament_title=tournament_title, limit=limit)


# ============================================
# CHAT ENDPOINT - Text-based AI Agent
# ============================================
# ============================================
# CHAT ENDPOINT - Claude 4 AI Agent with Tools
# ============================================

# System Prompt to define the AI's persona and context
SYSTEM_PROMPT = f"""You are 'Coach Rubberr', a world-class AI table tennis coach and analyst.
You help user '{PLAYER_NAME}' manage their table tennis career by analyzing match data, tracking progress, and finding tournaments.

CONCISENESS IS CRITICAL:
- Be extremely concise and direct. 
- Avoid long introductory summaries unless explicitly asked for a career summary.
- If the user says "hi", just say hi back and ask how you can help. 
- Do not dump all the user's stats, matches, and tournaments at once unless requested.
- Use tools ONLY to answer the specific question asked.

Persona:
- Professional, encouraging, and human-like.
- Provide psychological insights only when relevant to a specific match or trend being discussed.
- You are {PLAYER_NAME}'s personal coach. Be helpful but don't over-explain.

DATA STRATEGY:
1. ALWAYS start with `get_context` to see the current state.
2. If looking for a specific player's info (rating/rank), ALWAYS use `search_players` first.
3. Use `omnipong_player_search` ONLY as a fallback of last resort if the player is not found locally.
4. If the user asks about a specific match result, use `query_matches`.
"""


def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment")
    return anthropic.Anthropic(api_key=api_key)


# Tool definitions for Claude
CLAUDE_TOOLS = [
    {
        "name": "get_context",
        "description": "Get high-level summary context (user profile, recent matches, upcoming tournaments).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_stats",
        "description": "Get the player's current stats (win rate, trend, patterns) for USATT or Club League.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["usatt", "club"],
                    "description": "The data source.",
                }
            },
        },
    },
    {
        "name": "query_matches",
        "description": "Search the player's match history with filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "opponent_name": {
                    "type": "string",
                    "description": "Search for a specific opponent.",
                },
                "date_from": {"type": "string", "description": "YYYY-MM-DD format."},
                "result": {"type": "string", "enum": ["Win", "Loss"]},
            },
        },
    },
    {
        "name": "get_performance_analysis",
        "description": "Get deeper analysis of performance patterns (chokes/comebacks/set-by-set trends).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_players",
        "description": "Search our local database for a player's rating, USATT ID, and state. Use this before trying external searches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The player's name or USATT ID.",
                }
            },
        },
    },
    {
        "name": "omnipong_player_search",
        "description": "Look up a player's official USATT rating and USATT ID on OmniPong. USE ONLY IF search_players FAILS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {
                    "type": "string",
                    "description": "The name of the player to search for (e.g., 'Dawson, Jerry').",
                }
            },
            "required": ["player_name"],
        },
    },
    {
        "name": "omnipong_league_sync",
        "description": "Sync official USATT ratings and USATT IDs for all players in our league using OmniPong. This updates the local database with official data.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_practice_partners",
        "description": "Analyze match history to recommend the best practice partners based on skill level, competitiveness, and areas for improvement. Returns ranked list of opponents to focus practice time on.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of recommendations to return (default: 5)",
                }
            },
        },
    },
    {
        "name": "get_tournament_intelligence",
        "description": "Get AI-enhanced tournament recommendations with insights about difficulty, which events to enter, known players attending, and doubles partner suggestions. Analyzes tournament competition level and provides personalized guidance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tournament_title": {
                    "type": "string",
                    "description": "Optional: Filter by specific tournament name",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of tournaments to analyze (default: 5)",
                },
            },
        },
    },
]


async def get_claude_response(user_message: str, user_key: str = None):
    """
    Reusable logic to get a response from Claude 4 with tools.
    Used by /chat endpoint AND SMS webhook.
    user_key: caller's own Anthropic key (BYOK); if absent falls back to server key.
    """
    if user_key:
        client = anthropic.Anthropic(api_key=user_key)
    else:
        client = get_anthropic_client()

    # Use the model that we verified works (reverting to original)
    model = "claude-sonnet-4-5"

    messages = [{"role": "user", "content": user_message}]

    try:
        # Initial call to Claude
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=CLAUDE_TOOLS,
            messages=messages,
        )

        # Tool Handling Loop
        while response.stop_reason == "tool_use":
            tool_results = []

            messages.append({"role": "assistant", "content": response.content})

            for content_block in response.content:
                if content_block.type == "tool_use":
                    tool_name = content_block.name
                    tool_input = content_block.input
                    tool_id = content_block.id

                    print(f"DEBUG: Claude calling tool {tool_name} with {tool_input}")

                    # Tool Execution
                    result = {}
                    try:
                        if tool_name == "get_context":
                            result = get_agent_context()
                        elif tool_name == "get_stats":
                            result = get_stats(source=tool_input.get("source", "usatt"))
                        elif tool_name == "query_matches":
                            result = tool_query_matches(**tool_input)
                        elif tool_name == "get_performance_analysis":
                            result = get_tool_analysis()
                        elif tool_name == "search_players":
                            result = tool_search_players(PlayerSearch(**tool_input))
                        elif tool_name == "omnipong_player_search":
                            result = await browser_manager.search_omnipong_player(
                                tool_input.get("player_name")
                            )
                        elif tool_name == "omnipong_league_sync":
                            result = await tool_sync_league_players()
                        elif tool_name == "get_practice_partners":
                            result = get_practice_partners(
                                limit=tool_input.get("limit", 5)
                            )
                        elif tool_name == "get_tournament_intelligence":
                            result = get_tournament_intelligence(
                                tournament_title=tool_input.get("tournament_title"),
                                limit=tool_input.get("limit", 5),
                            )
                    except Exception as tool_err:
                        result = {"error": str(tool_err)}

                    tool_results.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_id,
                                    "content": json.dumps(result, default=str),
                                }
                            ],
                        }
                    )

            # Send tool results back to Claude
            messages.extend(tool_results)
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=CLAUDE_TOOLS,
                messages=messages,
            )

        # Get the final text response
        final_text = ""
        for block in response.content:
            if block.type == "text":
                final_text += block.text

        return final_text

    except Exception as e:
        print(f"Chat API Error: {e}")
        # FAIL LOUDLY as requested. Do not return friendly fallback.
        raise HTTPException(status_code=503, detail=f"AI Service Error: {str(e)}")


@app.post("/chat")
async def chat_endpoint(msg: ChatMessage, request: Request, _: None = Depends(_require_api_key)):
    response_text = await get_claude_response(msg.message, user_key=_get_user_ai_key(request))
    return {"response": response_text}


class PracticeReminder(BaseModel):
    partner_name: str
    reason: str = None


@app.post("/tools/remind_practice_partner")
def remind_practice_partner(reminder: PracticeReminder):
    """
    Send an SMS reminder to the user to practice with a specific partner.
    """
    session = SessionLocal()
    try:
        # 1. Get User Phone Number
        # Try DB first
        user = session.execute(text("SELECT * FROM users LIMIT 1")).fetchone()
        target_phone = None

        if user:
            # Check if phone col exists (it might not if migration failed/didn't run yet)
            # Safe access via dictionary
            u_dict = dict(user._mapping)
            target_phone = u_dict.get("phone_number")

        # Fallback to Env
        if not target_phone:
            target_phone = os.getenv("USER_PHONE_NUMBER")

        if not target_phone:
            return {
                "status": "error",
                "message": "No user phone number found. Please set USER_PHONE_NUMBER in .env or update settings.",
            }

        # 2. Construct Message
        msg_body = f"🏓 Coach Rubberr Reminder: You should practice with {reminder.partner_name}!"
        if reminder.reason:
            msg_body += f"\n\nContext: {reminder.reason}"

        # 3. Send SMS via Twilio
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        api_key = os.environ.get("TWILIO_API_KEY_SID")
        api_secret = os.environ.get("TWILIO_API_KEY_SECRET")
        from_phone = os.environ.get("TWILIO_PHONE_NUMBER")

        if not from_phone:
            return {"status": "error", "message": "Twilio phone number missing"}

        from twilio.rest import Client

        if api_key and api_secret and account_sid:
            client = Client(api_key, api_secret, account_sid)
        elif auth_token and account_sid:
            client = Client(account_sid, auth_token)
        else:
            return {"status": "error", "message": "Twilio credentials missing"}

        message = client.messages.create(
            body=msg_body, from_=from_phone, to=target_phone
        )

        return {
            "status": "success",
            "sid": message.sid,
            "message": f"Reminder sent to {target_phone}",
        }

    except Exception as e:
        print(f"Reminder Error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


class PhoneUpdate(BaseModel):
    phone_number: str


@app.post("/settings/update_phone")
def update_phone(data: PhoneUpdate):
    """Update the user's phone number in the database."""
    session = SessionLocal()
    try:
        # Check if user exists
        user_check = session.execute(text("SELECT id FROM users LIMIT 1")).fetchone()

        if user_check:
            # Update
            session.execute(
                text("UPDATE users SET phone_number = :p"), {"p": data.phone_number}
            )
        else:
            # Create dummy user if needed? Should exist.
            # Assuming the primary user exists from migration.
            pass

        session.commit()
        return {"status": "success", "message": "Phone number updated"}
    except Exception as e:
        # If column doesn't exist, this might fail.
        # We might need to alter table here if we really want to be robust, but strict schema usually managed outside.
        # Let's try to catch "no such column" and auto-migrate?
        if "no such column" in str(e).lower():
            try:
                session.rollback()
                session.execute(text("ALTER TABLE users ADD COLUMN phone_number TEXT"))
                session.commit()
                # Retry update
                session.execute(
                    text("UPDATE users SET phone_number = :p"), {"p": data.phone_number}
                )
                session.commit()
                return {
                    "status": "success",
                    "message": "Phone number updated (column created)",
                }
            except Exception as migrate_err:
                return {
                    "status": "error",
                    "message": f"Migration failed: {migrate_err}",
                }

        return {"status": "error", "message": str(e)}
    finally:
        session.close()


@app.get("/players/{player_name}/scouting")
async def get_player_scouting(player_name: str, _: None = Depends(_require_api_key)):
    """
    Generate an AI scouting report for a specific opponent based on match history.
    """
    session = SessionLocal()
    try:
        # 1. Fetch all matches against this opponent
        query = text("""
            SELECT date, winner_name, loser_name, result, score_summary, set_scores, source 
            FROM matches 
            WHERE opponent_name = :name
            ORDER BY date DESC
        """)
        result = session.execute(query, {"name": player_name})
        matches = [dict(row._mapping) for row in result]

        if not matches:
            return {
                "status": "error",
                "message": f"No match history found for {player_name}",
            }

        # 2. Extract basic stats
        wins = sum(
            1
            for m in matches
            if m["winner_name"] == PLAYER_FULL_NAME
            or m["result"] == "Win"
            or m["result"] == "W"
        )
        losses = len(matches) - wins

        # 3. Request AI Analysis
        match_summary = "\n".join(
            [
                f"- {m['date']}: {m['result']} ({m['score_summary']}) Sets: {m['set_scores']}"
                for m in matches
            ]
        )

        prompt = f"""
        You are a Table Tennis Scout. Analyze the following match history for '{PLAYER_FULL_NAME}' against '{player_name}'.

        MATCH HISTORY:
        {match_summary}

        TASK:
        1. Identify the opponent's likely style based on the results and scores (e.g., blocker, attacker, chopper).
        2. Highlight the player's vulnerabilities in these matches (e.g., "loses long rallies", "struggles in deciding sets").
        3. Provide 3 specific tactical "Keys to Victory" for the next match.
        4. Keep it concise, strategic, and professional.
        """

        scouting_report = await get_claude_response(prompt)

        return {
            "player_name": player_name,
            "stats": {
                "total_matches": len(matches),
                "record": f"{wins}-{losses}",
                "win_rate": f"{round(wins / len(matches) * 100)}%" if matches else "0%",
            },
            "analysis": scouting_report,
        }

    except Exception as e:
        print(f"Scouting Error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


@app.get("/training/recommendations")
async def get_training_recommendations():
    """
    Analyze global match history to suggest training focus areas and drills.
    """
    session = SessionLocal()
    try:
        # 1. Fetch stats for all matches
        # We'll use a simplified version of the logic inside /stats
        query = text("SELECT result, set_scores FROM matches")
        matches = session.execute(query).fetchall()

        total = len(matches)
        if total == 0:
            return {
                "status": "error",
                "message": "No match data available for analysis.",
            }

        comebacks = 0
        chokes = 0
        close_sets_won = 0
        close_sets_swung = 0

        for m in matches:
            res_str = m[0]
            sets_str = m[1]
            is_win = (
                res_str == "Win"
                or res_str == "W"
                or (
                    res_str
                    and "-" in res_str
                    and int(res_str.split("-")[0]) > int(res_str.split("-")[1])
                )
            )

            if sets_str:
                try:
                    set_list = [s.strip() for s in sets_str.split(",")]
                    parsed_sets = []
                    for s in set_list:
                        if "-" in s:
                            sp1, sp2 = map(int, s.split("-"))
                            parsed_sets.append((sp1, sp2))
                            if abs(sp1 - sp2) <= 2:
                                close_sets_swung += 1
                                if sp1 > sp2:
                                    close_sets_won += 1

                    if len(parsed_sets) > 0:
                        s1_user, s1_opp = parsed_sets[0]
                        won_first_set = s1_user > s1_opp
                        if not won_first_set and is_win:
                            comebacks += 1
                        elif won_first_set and not is_win:
                            chokes += 1
                except:
                    pass

        # 2. Construct prompt for training advice
        prompt = f"""
        You are Coach Rubberr, a world-class table tennis coach.
        Analyze the player's recent performance patterns across {total} matches and suggest a training plan.
        
        PATTERNS:
        - Comebacks (Won after losing Set 1): {comebacks}
        - Chokes (Lost after winning Set 1): {chokes}
        - Close Set Win Rate (sets decided by 2 pts): {round(close_sets_won / close_sets_swung * 100) if close_sets_swung > 0 else 0}%
        
        TASK:
        1. Identify the #1 psychological or physical weakness (e.g., "Pressure handling", "Slow starts").
        2. Recommend 2 specific drills (provide drill names and brief descriptions) to address these.
        3. Provide a motivational "Coach's Note."
        4. Keep it short, authoritative, and impactful.
        """

        advice = await get_claude_response(prompt)

        return {
            "total_matches": total,
            "patterns": {
                "comebacks": comebacks,
                "chokes": chokes,
                "clutch_percent": round(close_sets_won / close_sets_swung * 100)
                if close_sets_swung > 0
                else 0,
            },
            "coach_advice": advice,
        }

    except Exception as e:
        print(f"Training Error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
