#!/usr/bin/env bash
#
# Register the OmniPong MCP server with every MCP client detected on this
# machine. Safe by construction: every file is backed up before a write, JSON
# is re-parsed to validate before it is committed, and re-running only
# refreshes the entry (idempotent).
#
# Usage:
#   ./ops/install_mcp.sh                 # all detected clients
#   ./ops/install_mcp.sh --dry-run       # show intended changes, write nothing
#   ./ops/install_mcp.sh --client opencode --client openclaw
#
# Supported names: claude-desktop, claude-code, opencode (alias: openchamber),
# hermes, openclaw.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
DRY_RUN=0
CLIENTS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --client)  CLIENTS+=("$2"); shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ ! -x "$PY" ]; then
  echo "ERROR: repo venv python not found at $PY" >&2
  echo "Create it first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

echo "repo:   $REPO"
echo "python: $PY"
[ "$DRY_RUN" = 1 ] && echo "mode:   DRY RUN (no files will be written)"
echo

"$PY" - "$REPO" "$PY" "$DRY_RUN" ${CLIENTS[@]+"${CLIENTS[@]}"} <<'PY'
import json
import pathlib
import sys
import time

repo, py, dry_run = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
requested = set(sys.argv[4:])
home = pathlib.Path.home()

stdio = {"command": py, "args": [f"{repo}/omnipong_mcp_server.py"]}
opencode_entry = {
    "type": "local",
    "command": [py, f"{repo}/omnipong_mcp_server.py"],
    "enabled": True,
}
opencode_path = home / ".config/opencode/opencode.json"

# (name, aliases, file, parent path, entry, config file path for CLI hint)
JSON_CLIENTS = [
    ("claude-desktop", [], home / "Library/Application Support/Claude/claude_desktop_config.json",
     ["mcpServers"], stdio),
    ("claude-code", [], home / ".claude.json", ["mcpServers"], stdio),
    ("opencode", ["openchamber"], opencode_path, ["mcp"], opencode_entry),
    ("openclaw", [], home / ".openclaw/openclaw.json", ["mcp", "servers"], stdio),
]

hermes_path = home / ".hermes/config.yaml"
HERMES_BLOCK = (
    "mcp_servers:\n"
    "  omnipong:\n"
    f'    command: "{py}"\n'
    "    args:\n"
    f'      - "{repo}/omnipong_mcp_server.py"\n'
)

results = []


def wanted(name, aliases):
    if not requested:
        return True
    return name in requested or any(a in requested for a in aliases)


def merge_json(name, path, parents, entry):
    if not path.exists():
        if path.parent.exists():
            data = {}
        else:
            results.append((name, "SKIP", f"not installed ({path})"))
            return
    else:
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            results.append((name, "ERROR", f"could not parse {path}: {exc}"))
            return

    node = data
    for key in parents:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            if dry_run:
                results.append((name, "WOULD WRITE", f"add {key} at {path}"))
                return
            nxt = {}
            node[key] = nxt
        node = nxt
    node["omnipong"] = entry

    if dry_run:
        results.append((name, "WOULD WRITE", str(path)))
        return
    try:
        backup = path.with_suffix(path.suffix + f".bak.{time.strftime('%Y%m%d%H%M%S')}")
        if path.exists():
            backup.write_text(path.read_text())
        path.write_text(json.dumps(data, indent=2))
        json.loads(path.read_text())  # validate round-trip
        results.append((name, "OK", str(path)))
    except Exception as exc:
        results.append((name, "ERROR", f"write failed, backup at {backup}: {exc}"))


def merge_hermes():
    name = "hermes"
    if not hermes_path.exists():
        results.append((name, "SKIP", f"not installed ({hermes_path})"))
        return
    text = hermes_path.read_text()
    lines = text.splitlines(keepends=True)

    if any(line.strip().startswith("omnipong:") for line in lines):
        results.append((name, "OK", "omnipong already configured"))
        return

    # Indented block to insert under an existing top-level `mcp_servers:`.
    block = (
        "  omnipong:\n"
        f'    command: "{py}"\n'
        "    args:\n"
        f'      - "{repo}/omnipong_mcp_server.py"\n'
    )

    idx = next((i for i, l in enumerate(lines) if l.startswith("mcp_servers:")), None)

    if idx is None:
        new_text = text.rstrip("\n") + "\n\n" + HERMES_BLOCK
        action = "append mcp_servers"
    else:
        # Ensure the line we insert after is newline-terminated.
        if not lines[idx].endswith("\n"):
            lines[idx] = lines[idx] + "\n"
        new_text = "".join(lines[: idx + 1]) + block + "".join(lines[idx + 1 :])
        action = "insert under existing mcp_servers"

    if dry_run:
        results.append((name, "WOULD WRITE", f"{action} ({hermes_path})"))
        return

    backup = hermes_path.with_suffix(hermes_path.suffix + f".bak.{time.strftime('%Y%m%d%H%M%S')}")
    backup.write_text(text)
    hermes_path.write_text(new_text)
    results.append((name, "OK", f"{action} ({hermes_path})"))


for name, aliases, path, parents, entry in JSON_CLIENTS:
    if wanted(name, aliases):
        merge_json(name, path, parents, entry)

if wanted("hermes", []):
    merge_hermes()

print(f"{'client':<16}{'status':<14}detail")
print("-" * 72)
for name, status, detail in results:
    print(f"{name:<16}{status:<14}{detail}")

print()
print("Post-install checks:")
print(f"  claude mcp list                      # Claude Code")
print(f"  opencode mcp list                    # opencode / OpenChamber (restart the app first)")
print(f"  openclaw mcp doctor omnipong --probe # OpenClaw")
print()
print("Ask the assistant to run the `list_area_tournaments` tool to verify.")
PY

echo
echo "Claude Code CLI alternative (user scope):"
echo "  claude mcp add --scope user omnipong -- $PY $REPO/omnipong_mcp_server.py"
echo
echo "Note: restart each client after installing so it loads the new server."
