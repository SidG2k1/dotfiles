#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""orcw - one CLI for the whole lifecycle of an Orca orchestration run.

Wraps `orca orchestration` (and the worktree/terminal commands a coordinator
needs) so an agent runs a supervised multi-worker job in a handful of calls,
never hand-carries IDs, and never reads raw Orca JSON unless it asks to.

Design:
  * Orca is the source of truth. ~/.orcw is a cache plus a log, rebuilt from
    Orca by `orcw status --rebuild` / `orcw resume`.
  * Every Orca error is printed whole, with Orca's own nextSteps, then exit 1.
    No retries, no guessed flags. `orcw doctor` says what this Orca version
    lacks; a missing command disables the orcw commands that need it.
  * Output is compact text by default, projected JSON with --json, untouched
    Orca output with --raw.

Exit codes: 0 ok (a `wait` with no messages is ok), 1 Orca error, 2 orcw
refused (unanswered question on `done`, unresolved placeholder, settled
dispatch on `w done`), 3 doctor found a missing command or flag.

Written against Orca 1.4.194, verified on 1.4.196. Standard library only;
Python >= 3.9.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

PINNED = "1.4.194"
VERIFIED = {"1.4.194", "1.4.196"}
EXIT_OK, EXIT_ORCA, EXIT_REFUSED, EXIT_DOCTOR = 0, 1, 2, 3
WAIT_TYPES = "worker_done,escalation,question"
BODY_LIMIT = 1500
COLS = 120
SETTLED = {"completed", "failed", "stopped", "abandoned"}
LAUNCH_PREF_CAP = "orchestration.worker-launch-preferences.v1"


def home() -> Path:
    return Path(os.environ.get("ORCW_HOME") or (Path.home() / ".orcw"))


def orcw_cmd() -> str:
    """How a worker should invoke orcw: $ORCW_CMD, else bare name if on PATH, else this clone's launcher."""
    from shutil import which
    if os.environ.get("ORCW_CMD"):
        return os.environ["ORCW_CMD"]
    if which("orcw"):
        return "orcw"
    launcher = Path(__file__).resolve().parent.parent / "bin" / "orcw"
    return str(launcher) if launcher.exists() else "orcw"


# --------------------------------------------------------------------------- errors


class OrcaError(Exception):
    def __init__(self, error: Any, command: List[str], raw: str = ""):
        super().__init__(str(error))
        self.error, self.command, self.raw = error, command, raw

    def report(self) -> None:
        err = self.error if isinstance(self.error, dict) else {"message": str(self.error)}
        print("orca error:", file=sys.stderr)
        print(json.dumps(err, indent=2, sort_keys=True), file=sys.stderr)
        for step in err.get("nextSteps") or []:
            print(f"  next: {step}", file=sys.stderr)
        nca = err.get("nextCommandArgs")
        if nca:
            print("  run:  " + " ".join(shlex.quote(c) for c in orca_cmd() + list(nca)), file=sys.stderr)
        print("command: " + " ".join(shlex.quote(c) for c in self.command), file=sys.stderr)
        if self.raw.strip():
            print(self.raw.strip()[:4000], file=sys.stderr)


class Refused(Exception):
    pass


class DoctorFailed(Exception):
    pass


# --------------------------------------------------------------------------- adapter

_ORCA: Optional[List[str]] = None
_STATUS: Optional[Dict[str, Any]] = None


def orca_cmd() -> List[str]:
    global _ORCA
    if _ORCA is None:
        env = os.environ.get("ORCA_CLI_COMMAND")
        if env:
            _ORCA = shlex.split(env)
        elif os.environ.get("ORCA_DEV_REPO_ROOT"):
            _ORCA = ["orca-dev"]
        elif platform.system() == "Linux":
            _ORCA = ["orca-ide"]
        else:
            _ORCA = ["orca"]
    return _ORCA


def parse_stream(text: str) -> List[Any]:
    """Parse stdout as a stream of JSON documents; ignore trailing non-JSON."""
    dec = json.JSONDecoder()
    docs: List[Any] = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        try:
            obj, i = dec.raw_decode(text, i)
        except ValueError:
            break
        if isinstance(obj, dict) and (obj.get("_keepalive") or obj.get("_heartbeat")):
            continue
        docs.append(obj)
    return docs


def orca(*args: Any, timeout: Optional[float] = None, allow_fail: bool = False) -> List[Any]:
    cmd = orca_cmd() + [str(a) for a in args]
    if "--json" not in cmd:
        cmd.append("--json")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise OrcaError({"code": "orca_not_found", "message": str(exc)}, cmd)
    except subprocess.TimeoutExpired as exc:
        partial = parse_stream(exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        req = next((d.get("id") for d in partial if isinstance(d, dict) and d.get("id")), None)
        err: Dict[str, Any] = {
            "code": "orcw_timeout",
            "message": f"no answer after {timeout}s; the command may still have taken effect",
            "nextSteps": ["Inspect state before retrying: orcw status --rebuild"],
        }
        if req:
            err["requestId"] = req
            err["nextSteps"].append(f"Ask Orca whether it landed: orcw request {req}")
        raise OrcaError(err, cmd)
    docs = parse_stream(proc.stdout)
    record_dir = os.environ.get("ORCW_RECORD")
    if record_dir:
        rec_path = Path(record_dir)
        rec_path.mkdir(parents=True, exist_ok=True)
        n = len(list(rec_path.glob("*.json"))) + 1
        name = "-".join(a for a in cmd[len(orca_cmd()):] if not a.startswith("-"))[:60] or "orca"
        (rec_path / f"{n:03d}-{name}.json").write_text(json.dumps(
            {"args": cmd[len(orca_cmd()):], "exit": proc.returncode, "stdout": docs, "stderr": proc.stderr[-2000:]}, indent=2))
    if not docs:
        raise OrcaError(
            {"code": "no_json_output", "message": "orca printed no JSON", "exit": proc.returncode},
            cmd,
            proc.stdout + proc.stderr,
        )
    if not allow_fail:
        for doc in docs:
            if isinstance(doc, dict) and doc.get("ok") is False:
                raise OrcaError(doc.get("error") or doc, cmd)
    log_event("orca", {"args": cmd[len(orca_cmd()):], "exit": proc.returncode})
    return docs


def orca_text(*args: Any) -> str:
    cmd = orca_cmd() + [str(a) for a in args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise OrcaError({"code": "orca_not_found", "message": str(exc)}, cmd)
    return proc.stdout + proc.stderr


def result(docs: List[Any]) -> Dict[str, Any]:
    for doc in reversed(docs):
        if isinstance(doc, dict) and "result" in doc:
            return doc["result"] if isinstance(doc["result"], dict) else {"value": doc["result"]}
    return docs[-1] if docs and isinstance(docs[-1], dict) else {}


def get(obj: Any, *paths: str, default: Any = None) -> Any:
    """First non-None value at any dotted path."""
    for path in paths:
        cur = obj
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = None
                break
        if cur is not None:
            return cur
    return default


def status() -> Dict[str, Any]:
    global _STATUS
    if _STATUS is None:
        res = result(orca("status"))
        _STATUS = {
            "version": get(res, "runtime.appVersion", default="unknown"),
            "capabilities": get(res, "runtime.capabilities", default=[]) or [],
            "running": bool(get(res, "app.running", default=False)),
        }
    return _STATUS


def help_text(group: str, cmd: Optional[str] = None) -> str:
    """`orca <group> [<cmd>] --help`, cached per app version."""
    cache = home() / "cache" / status()["version"] / f"{group}{'-' + cmd if cmd else ''}.txt"
    if cache.exists():
        return cache.read_text()
    text = orca_text(*([group, cmd, "--help"] if cmd else [group, "--help"]))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text)
    return text


def has_flag(group: str, cmd: str, flag: str) -> bool:
    return flag in help_text(group, cmd)


def has_cap(cap: str) -> bool:
    return cap in status()["capabilities"]


# --------------------------------------------------------------------------- cache + log


def current_run() -> Optional[str]:
    path = home() / "current"
    return path.read_text().strip() if path.exists() else None


def set_current(run: str) -> None:
    home().mkdir(parents=True, exist_ok=True)
    (home() / "current").write_text(run + "\n")


def run_path(run: str) -> Path:
    return home() / "runs" / f"{run}.json"


def load_run(run: str) -> Dict[str, Any]:
    path = run_path(run)
    if path.exists():
        data = json.loads(path.read_text())
        data.setdefault("deferred", [])
        data.setdefault("questions", {})
        return data
    return {"run": run, "tasks": {}, "replied": [], "delivery": None, "cursors": {}, "deferred": [], "questions": {}}


def save_run(data: Dict[str, Any]) -> None:
    run = data["run"]
    run_path(run).parent.mkdir(parents=True, exist_ok=True)
    run_path(run).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tasks_dir = home() / "runs" / run / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for task_id, rec in data["tasks"].items():
        target = tasks_dir / f"{task_id}.json"
        content = json.dumps(dict(rec, task=task_id, run=run), indent=2) + "\n"
        if not target.exists() or target.read_text() != content:
            target.write_text(content)


def log_event(kind: str, data: Dict[str, Any]) -> None:
    run = current_run()
    if not run:
        return
    path = home() / "runs" / run / "log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, **data}) + "\n")


def save_body(run: Optional[str], msg_id: str, body: str) -> Optional[Path]:
    if not run:
        return None
    path = home() / "runs" / run / "messages" / f"{msg_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def require_run(ns: argparse.Namespace) -> str:
    run = getattr(ns, "run", None) or current_run()
    if not run:
        raise Refused("no current run: `orcw run \"<objective>\"` first, or pass --run <id>")
    return run


# --------------------------------------------------------------------------- projections

PROJECTIONS: Dict[str, Dict[str, List[str]]] = {
    "run": {"run": ["run.id", "runId", "id"], "objective": ["run.objective", "objective"]},
    "worktree": {
        "worktree": ["worktree.id", "id"],
        "path": ["worktree.path", "path"],
        "branch": ["worktree.branch", "worktree.git.branch", "branch"],
        "handle": ["agentTerminalHandle", "worktree.agentTerminalHandle", "startupTerminal.handle"],
    },
    "task_create": {"task": ["task.id", "taskId", "id"]},
    "worker_start": {
        "dispatch": ["dispatch.id", "dispatchId", "worker.dispatch_id", "worker.dispatchId"],
        "handle": ["worker.agent_terminal_handle", "worker.agentTerminalHandle", "agentTerminalHandle",
                   "dispatch.assignee_handle", "terminal.handle", "agentTerminal.handle"],
        "state": ["worker.state", "state", "stage"],
        "launch": ["launch.effective", "worker.launch.effective"],
    },
    "worker": {
        "dispatch": ["dispatchId", "dispatch.id", "worker.dispatch_id"],
        "state": ["workerState", "worker.state", "state"],
        "terminal_state": ["terminalState", "worker.terminal_state"],
        "handle": ["agentTerminalHandle", "worker.agent_terminal_handle", "worker.agentTerminalHandle"],
        "agentWait": ["observation.agentWait"],
    },
    "dispatch": {
        "dispatch": ["dispatch.id"],
        "task": ["dispatch.task_id"],
        "run": ["dispatch.run_id"],
        "status": ["dispatch.status"],
        "handle": ["dispatch.assignee_handle"],
    },
    "delivery": {"delivery": ["deliveryId", "delivery.id", "delivery_id"], "count": ["count"]},
    "message": {
        "id": ["id"],
        "type": ["type"],
        "subject": ["subject"],
        "body": ["body"],
        "from": ["from_handle"],
        "payload": ["payload"],
    },
    "release": {"state": ["terminalState", "state", "status"], "reason": ["reason", "detail", "code"]},
    "task_row": {
        "task": ["id"],
        "status": ["status"],
        "title": ["task_title", "display_name"],
        "result": ["result"],
        "deps": ["deps"],
    },
    "send": {"message": ["message.id", "messageId", "id"]},
    "ask": {
        "message": ["message.id", "messageId", "questionId", "question.id"],
        "answer": ["answer", "reply.body", "reply", "response"],
        "status": ["status", "state"],
    },
    "read": {"cursor": ["cursor"], "source": ["source"], "rows": ["terminal.tail", "transcript", "rows", "lines", "output"],
             "worker": ["status.worker"], "terminal": ["status.terminal"], "warnings": ["warnings"]},
}


def project(obj: Any, name: str) -> Dict[str, Any]:
    return {key: get(obj, *paths) for key, paths in PROJECTIONS[name].items()}


def receipt_handle(res: Dict[str, Any], dispatch: Optional[str]) -> Optional[str]:
    """Agent terminal handle from a worker-start receipt: projected paths, then the
    effects list, then worker-show as the authoritative fallback."""
    handle = project(res, "worker_start")["handle"]
    if handle:
        return handle
    for eff in get(res, "worker.effects", "effects", default=[]) or []:
        if isinstance(eff, dict) and eff.get("kind") == "terminal" and eff.get("role") == "agent" and eff.get("id"):
            return eff["id"]
    if dispatch:
        shown = result(orca("orchestration", "worker-show", "--dispatch", dispatch))
        return project(shown, "worker")["handle"] or project(shown, "dispatch")["handle"]
    return None


def parse_payload(msg: Dict[str, Any]) -> Dict[str, Any]:
    payload = msg.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = {}
    return payload if isinstance(payload, dict) else {}


def message_view(msg: Dict[str, Any]) -> Dict[str, Any]:
    view = project(msg, "message")
    payload = parse_payload(msg)
    view["task"] = payload.get("taskId")
    view["dispatch"] = payload.get("dispatchId")
    view["outcome"] = payload.get("outcome")
    view["files"] = payload.get("filesModified")
    view["rejected"] = view["type"] == "worker_done" and str(view["subject"] or "").startswith("Rejected worker_done")
    return view


# --------------------------------------------------------------------------- output


def trunc(text: Any, width: int = COLS) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def cut(text: str, width: int = COLS) -> str:
    """Like trunc but keeps internal spacing (for aligned rows)."""
    return text if len(text) <= width else text[: width - 1] + "…"


def tilde(path: Any) -> str:
    text = str(path or "?")
    home_dir = str(Path.home())
    return "~" + text[len(home_dir):] if text.startswith(home_dir) else text


def emit(ns: argparse.Namespace, projected: Any, raw: List[Any], lines: List[str]) -> None:
    if getattr(ns, "raw", False):
        print(json.dumps(raw, indent=2))
    elif getattr(ns, "json", False):
        print(json.dumps(projected, indent=2, sort_keys=True, default=str))
    else:
        for line in lines:
            print(line)


def body_lines(run: Optional[str], msg_id: str, body: str, full: bool) -> List[str]:
    body = body or ""
    saved = save_body(run, msg_id, body) if len(body) > BODY_LIMIT else None
    shown = body if full or len(body) <= BODY_LIMIT else body[:BODY_LIMIT]
    lines = ["    " + ln for ln in shown.splitlines()] if shown.strip() else []
    if saved and not full:
        lines.append(f"    … {len(body) - BODY_LIMIT} more chars; --full or {saved}")
    return lines


def message_lines(run: Optional[str], msg: Dict[str, Any], full: bool) -> List[str]:
    view = message_view(msg)
    kind = view["type"] or "?"
    if view["rejected"]:
        head = f"REJECT {view['task']}  Orca refused this worker_done; the task is NOT settled  | {trunc(view['subject'], 50)}"
    elif kind == "worker_done":
        head = f"done   {view['task']}  {view['outcome']}  | {trunc(view['subject'], 70)}"
    elif kind == "question":
        head = f"ask    {view['id']}  from {view['task'] or view['from']}  | {trunc(view['subject'], 60)}"
    elif kind == "escalation":
        head = f"escal  {view['task'] or view['from']}  | {trunc(view['subject'], 70)}"
    else:
        head = f"{kind:<6} {view['task'] or view['from']}  | {trunc(view['subject'], 70)}"
    return [head] + body_lines(run, view["id"] or "msg", view["body"] or "", full)


# --------------------------------------------------------------------------- helpers


def duration(text: str) -> int:
    """'15m' | '900s' | '1h' | '900' -> seconds."""
    m = re.fullmatch(r"(\d+)([smh]?)", text.strip())
    if not m:
        raise Refused(f"bad duration {text!r}; use 900, 900s, 15m, or 1h")
    n, unit = int(m.group(1)), m.group(2)
    return n * {"": 1, "s": 1, "m": 60, "h": 3600}[unit]


def git(path: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def strip_ref(branch: Any) -> Optional[str]:
    if not branch:
        return None
    return str(branch).replace("refs/heads/", "")


def read_spec(source: str) -> str:
    return sys.stdin.read() if source == "-" else Path(source).read_text()


def find_handle(worktree_id: str) -> Optional[str]:
    res = result(orca("terminal", "list", "--worktree", f"id:{worktree_id}"))
    terms = res.get("terminals") or []
    agents = [t for t in terms if t.get("agentIdentity")] or terms
    return agents[0].get("handle") if agents else None


def worktree_by_path(path: str) -> Optional[Dict[str, Any]]:
    res = result(orca("worktree", "list"))
    real = os.path.realpath(path)
    for wt in res.get("worktrees") or []:
        if os.path.realpath(wt.get("path") or "") == real:
            return wt
    return None


def resolve_dispatch(ns: argparse.Namespace, ref: str) -> str:
    if ref.startswith("ctx_"):
        return ref
    run = require_run(ns)
    data = load_run(run)
    rec = data["tasks"].get(ref)
    if rec and rec.get("dispatch"):
        return rec["dispatch"]
    view = project(result(orca("orchestration", "dispatch-show", "--task", ref)), "dispatch")
    if not view["dispatch"]:
        raise Refused(f"{ref} has no dispatch")
    data["tasks"].setdefault(ref, {})["dispatch"] = view["dispatch"]
    data["tasks"][ref].setdefault("handle", view["handle"])
    save_run(data)
    return view["dispatch"]


def task_rows(run: str, brief: bool = True) -> List[Dict[str, Any]]:
    args = ["orchestration", "task-list", "--run", run]
    if brief and has_flag("orchestration", "task-list", "--brief"):
        args.append("--brief")
    return result(orca(*args)).get("tasks") or []


def task_result(row: Dict[str, Any]) -> Dict[str, Any]:
    res = row.get("result")
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except ValueError:
            res = {"body": res}
    return res if isinstance(res, dict) else {}


# --------------------------------------------------------------------------- spec files

PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z_]+)\s*}}")
KNOWN_SUBS = {"branch", "path", "repo", "run", "base_commit", "name"}

POLICIES = {
    "unstaged": "leave every change uncommitted in the worktree; do not commit or push",
    "commit": "commit on this branch with clear messages; do not push",
    "pr": "commit, push this branch, and open a PR against the repo default base",
}


def trailer(kind: str, subs: Dict[str, str], ctx: List[str], policy: str, report: Optional[str]) -> str:
    cmd = orcw_cmd()
    lines = ["---", "## Working agreement (generated by orcw)"]
    if kind == "task":
        if cmd != "orcw":
            lines.append(f"`orcw` is not on PATH here. Every `orcw` below means `{cmd}`.")
        lines += [
            "FIRST: paste your whole preamble (from \"You are working inside Orca\" up to and including the",
            "\"=== TASK ===\" line) into this command; it stores the two values Orca needs and prints what it resolved:",
            "",
            f"    {cmd} w init --preamble-file - <<'PREAMBLE'",
            "    <paste the preamble here>",
            "    PREAMBLE",
            "",
            "After that, the preamble's raw `orca orchestration ...` commands are superseded by the `orcw w` commands",
            "below; do not run them. Only the two values (--from and --dispatch-capability) are used, and init took them.",
        ]
    lines.append(f"Worktree: {subs.get('path', '?')}  branch: {subs.get('branch', '?')}  base: {subs.get('base_commit', '?')}")
    if ctx:
        lines.append("Read first: " + ", ".join(ctx))
    lines.append(f"Commit policy: {policy} - {POLICIES[policy]}.")
    lines.append("Do not add AI-generation branding to commits, PR text, or files.")
    if kind == "task":
        lines += [
            "Every 5 minutes while working: `orcw w heartbeat <investigating|implementing|reviewing|waiting>`.",
            "Decisions the spec does not settle: `orcw w ask \"<question>\" --options a,b`. Never guess.",
            "Before any irreversible step (push, PR, tag, apply, delete): `orcw w mail`, and act on what it says.",
            "Scratch files (reports, notes) go under $TMPDIR or the path the spec names, never into the worktree.",
            "When finished: `orcw w done --ok|--failed \"<subject>\" --body <file> [--files <csv>]`, once, then idle.",
            "  (--files lists paths you changed; omit it when you changed nothing.)",
            "The done body must contain: " + (report or "what changed, what you found, what remains, and any URL"),
        ]
    else:
        lines.append("This is a full handoff: you own the work. No coordinator is waiting; do not send lifecycle messages.")
    return "\n".join(lines) + "\n"


def render_spec(text: str, kind: str, subs: Dict[str, str], ctx: List[str], policy: str, report: Optional[str]) -> str:
    text = PLACEHOLDER.sub(lambda m: subs.get(m.group(1), m.group(0)), text)
    left = sorted({m.group(1) for m in PLACEHOLDER.finditer(text)})
    if left:
        raise Refused("unresolved placeholders: " + ", ".join("{{" + k + "}}" for k in left))
    return text.rstrip() + "\n\n" + trailer(kind, subs, ctx, policy, report)


def lint_spec(text: str) -> List[str]:
    warnings = []
    unknown = sorted({m.group(1) for m in PLACEHOLDER.finditer(text)} - KNOWN_SUBS)
    if unknown:
        raise Refused("unknown placeholders: " + ", ".join("{{" + k + "}}" for k in unknown)
                      + "; known: " + ", ".join(sorted(KNOWN_SUBS)))
    if len(text) > 6000:
        warnings.append(f"spec is {len(text)} chars; workers read long specs badly, consider --context files")
    if not text.strip():
        raise Refused("spec is empty")
    return warnings


# --------------------------------------------------------------------------- doctor

USED: Dict[str, Dict[str, List[str]]] = {
    "orchestration": {
        "run-create": ["--objective"],
        "run-current": [],
        "task-create": ["--spec", "--task-title", "--display-name", "--run"],
        "task-list": ["--run"],
        "worker-start": ["--task", "--terminal", "--worktree", "--agent", "--run"],
        "worker-show": ["--dispatch"],
        "worker-read": ["--dispatch", "--limit"],
        "worker-list": ["--run"],
        "worker-release": ["--dispatch"],
        "dispatch": ["--task", "--to", "--inject", "--run"],
        "dispatch-show": ["--task"],
        "check": ["--wait", "--types", "--timeout-ms", "--ack", "--peek", "--run"],
        "send": ["--to", "--subject", "--body", "--type", "--task-id", "--dispatch-id", "--outcome", "--files-modified"],
        "reply": ["--id", "--body"],
        "ask": ["--question", "--options", "--timeout-ms", "--resume"],
    },
    "worktree": {
        "create": ["--name", "--repo", "--agent", "--prompt", "--setup", "--base-branch", "--no-parent"],
        "list": [],
        "rm": ["--worktree"],
        "show": ["--worktree"],
        "set": ["--worktree", "--comment"],
    },
    "terminal": {"wait": ["--terminal", "--for", "--timeout-ms"], "list": ["--worktree"]},
}


OPTIONAL: Dict[str, Dict[str, List[str]]] = {
    "orchestration": {"request-show": ["--request"]},  # 1.4.196+: lost-response recovery
}


def doctor_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    st = status()
    if st["version"] in VERIFIED:
        note = f"app {st['version']}"
    else:
        note = f"app {st['version']} (orcw verified on {', '.join(sorted(VERIFIED))})"
    rows.append({"check": "orca status", "state": "ok" if st["running"] else "degraded", "note": note})
    probe = orca("orchestration", "run-current", allow_fail=True)
    err = next((d.get("error") for d in probe if isinstance(d, dict) and d.get("ok") is False), None)
    if err and (err.get("code") not in ("run_required",)):
        rows.append({"check": "orchestration enabled", "state": "degraded",
                     "note": f"{err.get('code')}: {err.get('message', '')}"})
    else:
        rows.append({"check": "orchestration enabled", "state": "ok", "note": "Settings > Experimental"})
    for group, cmds in USED.items():
        group_help = help_text(group)
        for cmd, flags in cmds.items():
            if not re.search(rf"^\s+{re.escape(cmd)}\s", group_help, re.M):
                rows.append({"check": f"{group} {cmd}", "state": "missing",
                             "note": f"run: {' '.join(orca_cmd())} {group} --help"})
                continue
            text = help_text(group, cmd)
            lost = [f for f in flags if f not in text]
            if lost:
                rows.append({"check": f"{group} {cmd}", "state": "missing",
                             "note": "flags " + " ".join(lost) + f"; run: {' '.join(orca_cmd())} {group} {cmd} --help"})
            else:
                rows.append({"check": f"{group} {cmd}", "state": "ok", "note": ""})
    for group, cmds in OPTIONAL.items():
        group_help = help_text(group)
        for cmd, flags in cmds.items():
            present = re.search(rf"^\s+{re.escape(cmd)}\s", group_help, re.M) and all(
                f in help_text(group, cmd) for f in flags)
            rows.append({"check": f"{group} {cmd}", "state": "ok" if present else "degraded",
                         "note": "" if present else "optional; `orcw request` unavailable on this Orca"})
    rows.append({"check": "worker --model/--effort", "state": "ok" if has_cap(LAUNCH_PREF_CAP) else "degraded",
                 "note": LAUNCH_PREF_CAP})
    return rows


def doctor_ok_marker() -> Path:
    return home() / "cache" / status()["version"] / "doctor.ok"


def ensure_doctor() -> None:
    if doctor_ok_marker().exists():
        return
    rows = doctor_rows()
    missing = [r for r in rows if r["state"] == "missing"]
    if missing:
        for r in missing:
            print(f"doctor: missing {r['check']}: {r['note']}", file=sys.stderr)
        raise DoctorFailed("this Orca lacks commands orcw needs; see `orcw doctor`")
    doctor_ok_marker().parent.mkdir(parents=True, exist_ok=True)
    doctor_ok_marker().write_text("ok\n")


def cmd_doctor(ns: argparse.Namespace) -> int:
    rows = doctor_rows()
    width = max(len(r["check"]) for r in rows)
    lines = [f"{r['state']:<9} {r['check']:<{width}}  {r['note']}".rstrip() for r in rows]
    emit(ns, rows, [], lines)
    missing = any(r["state"] == "missing" for r in rows)
    if not missing:
        doctor_ok_marker().parent.mkdir(parents=True, exist_ok=True)
        doctor_ok_marker().write_text("ok\n")
    return EXIT_DOCTOR if missing else EXIT_OK


# --------------------------------------------------------------------------- coordinator commands


def cmd_run(ns: argparse.Namespace) -> int:
    ensure_doctor()
    docs = orca("orchestration", "run-create", "--objective", ns.objective)
    view = project(result(docs), "run")
    if not view["run"]:
        raise OrcaError({"code": "orcw_projection", "message": "run-create returned no run id; see --raw"}, ["run-create"])
    set_current(view["run"])
    data = load_run(view["run"])
    data["objective"] = ns.objective
    save_run(data)
    log_event("run", {"run": view["run"], "objective": ns.objective})
    lines = [f"run    {view['run']}  | {trunc(ns.objective, 90)}"]
    if ns.comment:
        try:
            orca("worktree", "set", "--worktree", "active", "--comment", f"orcw {view['run']}: {ns.objective}"[:200])
        except OrcaError as exc:
            lines.append(f"note   could not set worktree comment ({get(exc.error, 'code', default='error')}); harmless")
    emit(ns, view, docs, lines)
    return EXIT_OK


LOST = {"runtime_unavailable", "orcw_timeout", "no_json_output"}
TASK_OPTS = ["repo", "name", "base", "child", "into", "agent", "model", "effort", "setup",
             "context", "commit_policy", "report", "title", "deps", "after", "share"]
LIVE_STATES = {"dispatched", "unassigned", "pending", "ready"}


def live_tasks_at(data: Dict[str, Any], path: Optional[str]) -> List[str]:
    if not path:
        return []
    real = os.path.realpath(path)
    return [t for t, r in data["tasks"].items()
            if r.get("status") in LIVE_STATES and r.get("path") and os.path.realpath(r["path"]) == real]


def upstream_state(run: str, after: List[str]) -> Dict[str, Any]:
    """{'pending': [...], 'bodies': {task: body}}; refuses on a missing or failed upstream."""
    rows = {r.get("id"): r for r in task_rows(run, brief=False)}
    pending, bodies = [], {}
    for up in after:
        row = rows.get(up)
        if not row:
            raise Refused(f"--after {up}: no such task in run {run}")
        if row.get("status") == "failed":
            raise Refused(f"--after {up}: upstream task failed; fix or retry it first")
        if row.get("status") == "completed":
            res = task_result(row)
            bodies[up] = res.get("body") or res.get("subject") or json.dumps(res)
        else:
            pending.append(up)
    return {"pending": pending, "bodies": bodies}


def worktree_by_name(name: str) -> Optional[Dict[str, Any]]:
    res = result(orca("worktree", "list"))
    for wt in res.get("worktrees") or []:
        if wt.get("displayName") == name or str(wt.get("path") or "").rstrip("/").endswith("/" + name):
            return wt
    return None


def create_worktree(o: Any, agent: Optional[str], prompt: Optional[str]) -> Dict[str, Any]:
    args = ["worktree", "create", "--name", o.name, "--setup", o.setup]
    if o.repo:
        args += ["--repo", o.repo if ":" in o.repo else f"name:{o.repo}"]
    if o.base:
        args += ["--base-branch", o.base]
    if not getattr(o, "child", False):
        args.append("--no-parent")
    if agent:
        args += ["--agent", agent]
    if prompt:
        args += ["--prompt", prompt]
    try:
        docs = orca(*args)
    except OrcaError as exc:
        # Lost response: the create may have landed. Look before failing.
        if get(exc.error, "code") not in LOST:
            raise
        found = worktree_by_name(o.name)
        if not found:
            raise
        view = project(found, "worktree")
        view["branch"] = strip_ref(view["branch"])
        view["handle"] = find_handle(view["worktree"]) if agent else None
        view["base_commit"] = git(view["path"], "rev-parse", "HEAD") or None
        view["raw"] = [found]
        view["recovered"] = f"{get(exc.error, 'code')}; worktree found by name afterwards"
        return view
    view = project(result(docs), "worktree")
    view["branch"] = strip_ref(view["branch"])
    if not view["worktree"] or not view["path"]:
        raise OrcaError({"code": "orcw_projection", "message": "worktree create returned no id/path; see --raw"}, args)
    if agent and not view["handle"]:
        view["handle"] = find_handle(view["worktree"])
    if not view["branch"]:
        view["branch"] = git(view["path"], "rev-parse", "--abbrev-ref", "HEAD") or None
    view["base_commit"] = git(view["path"], "rev-parse", "HEAD") or None
    view["raw"] = docs
    return view


def existing_worktree(selector: str) -> Dict[str, Any]:
    sel = selector if ":" in selector or selector in ("active", "current") else f"path:{selector}"
    docs = orca("worktree", "show", "--worktree", sel)
    view = project(result(docs), "worktree")
    view["branch"] = strip_ref(view["branch"])
    view["base_commit"] = git(view["path"], "rev-parse", "HEAD") if view["path"] else None
    view["selector"] = sel
    view["raw"] = docs
    return view


def create_task_row(run: str, text: str, title: str, deps: Optional[List[str]]) -> str:
    tc = ["orchestration", "task-create", "--run", run, "--spec", text, "--task-title", title, "--display-name", title]
    if deps:
        tc += ["--deps", json.dumps(deps)]
    try:
        task_id = project(result(orca(*tc)), "task_create")["task"]
    except OrcaError as exc:
        if get(exc.error, "code") not in LOST:
            raise
        rows = [r for r in task_rows(run) if r.get("task_title") == title and r.get("status") in ("pending", "ready")]
        if not rows:
            raise
        task_id = rows[-1].get("id")
        print(f"note   task-create response lost; reusing {task_id} found by title", file=sys.stderr)
    if not task_id:
        raise OrcaError({"code": "orcw_projection", "message": "task-create returned no task id; see --raw"}, tc)
    return task_id


def start_task(ns: argparse.Namespace, run: str, data: Dict[str, Any], o: Any, spec: str,
               bodies: Dict[str, str], existing: Optional[str] = None,
               collect: Optional[List[str]] = None) -> int:
    """Place the worker, render the spec, create the task row, attach the worker."""
    notes: List[str] = []
    if o.into or not o.name:
        wt = existing_worktree(o.into or "current")
        mode = "existing"
    elif o.model:
        wt = create_worktree(o, agent=None, prompt=None)
        mode = "new-model"
        notes.append("note   bare worktree create may open a fallback shell tab; only the agent handle is used")
    else:
        wt = create_worktree(o, agent=o.agent, prompt=None)
        mode = "new-agent"
    if wt.get("recovered"):
        notes.append(f"note   worktree create: {wt['recovered']}")
        mode = "existing" if not wt.get("handle") else mode
        wt.setdefault("selector", f"id:{wt['worktree']}")
    busy = [t for t in live_tasks_at(data, wt.get("path")) if t != existing]
    if busy and not getattr(o, "share", False):
        raise Refused(f"{tilde(wt.get('path'))} already has a live worker ({', '.join(busy)}). Two agents editing one "
                      f"checkout collide; use --name <new-worktree>, --in <other>, or --share to accept it")
    if busy:
        notes.append(f"note   sharing {tilde(wt.get('path'))} with live task(s) {', '.join(busy)}")

    if existing:
        task_id = existing
        title = data["tasks"].get(existing, {}).get("title") or existing
    else:
        subs = {"branch": wt.get("branch") or "?", "path": wt.get("path") or "?", "repo": o.repo or "",
                "run": run, "base_commit": wt.get("base_commit") or "?", "name": o.name or ""}
        text = render_spec(spec, "task", subs, o.context, o.commit_policy, o.report)
        if bodies:
            pre = "\n\n".join(f"## Upstream result ({up})\n\n{body.rstrip()}" for up, body in bodies.items())
            text = f"{pre}\n\n---\n\n{text}"
        title = o.title
        task_id = create_task_row(run, text, title, o.deps)
        data["tasks"][task_id] = {"status": "unassigned", "title": title, "name": o.name, "repo": o.repo}
        save_run(data)

    handle = wt.get("handle")
    ws = ["orchestration", "worker-start", "--task", task_id, "--run", run]
    if mode == "new-agent" and handle:
        orca("terminal", "wait", "--terminal", handle, "--for", "tui-idle", "--timeout-ms", "60000", allow_fail=True)
        ws += ["--terminal", handle]
    else:
        ws += ["--worktree", wt.get("selector") or f"id:{wt['worktree']}", "--agent", o.agent]
        if o.model:
            ws += ["--model", o.model]
        if o.effort:
            ws += ["--effort", o.effort]
    try:
        res = result(orca(*ws))
    except OrcaError as exc:
        exc.report()
        print(f"task   {task_id} exists but has no worker. Retry placement with: "
              f"orcw task --existing {task_id} --in <worktree> [--agent ...]", file=sys.stderr)
        return EXIT_ORCA
    dispatch = project(res, "worker_start")["dispatch"]
    handle = receipt_handle(res, dispatch) or handle

    rec = {
        "dispatch": dispatch, "handle": handle, "worktree": wt.get("worktree"), "path": wt.get("path"),
        "branch": wt.get("branch"), "base_commit": wt.get("base_commit"), "supervised": True,
        "name": o.name, "repo": o.repo, "title": title, "status": "dispatched",
    }
    data["tasks"][task_id] = rec
    save_run(data)
    log_event("task", {"task": task_id, **rec})
    view = dict(rec, task=task_id, run=run)
    lines = [
        f"task   {task_id}  dispatch {dispatch}  supervised",
        f"where  {tilde(wt.get('path'))}  branch {wt.get('branch')}  base {str(wt.get('base_commit'))[:12]}",
        f"agent  {handle}",
    ] + notes
    if collect is not None:
        collect.extend(lines)
    else:
        emit(ns, view, wt.get("raw", []), lines)
    return EXIT_OK


def cmd_task(ns: argparse.Namespace) -> int:
    ensure_doctor()
    run = require_run(ns)
    data = load_run(run)
    if bool(ns.model or ns.effort) and not has_cap(LAUNCH_PREF_CAP):
        raise Refused(f"--model/--effort need capability {LAUNCH_PREF_CAP}; this Orca lacks it")
    if ns.effort and not ns.model:
        raise Refused("--effort requires --model")
    if ns.into and ns.name:
        raise Refused("--in and --name are exclusive: attach to an existing worktree or create one")
    o = SimpleNamespace(**{k: getattr(ns, k) for k in TASK_OPTS})
    if ns.existing:
        if ns.existing not in {r.get("id") for r in task_rows(run)}:
            raise Refused(f"--existing {ns.existing}: no such task in run {run}")
        return start_task(ns, run, data, o, "", {}, existing=ns.existing)
    if not ns.spec:
        raise Refused("--spec is required (or --existing <task>)")
    spec = read_spec(ns.spec)
    lint_spec(spec)
    o.title = ns.title or next((ln.lstrip("# ").strip() for ln in spec.splitlines() if ln.strip()), "task")[:80]
    bodies: Dict[str, str] = {}
    if ns.after:
        state = upstream_state(run, ns.after)
        if state["pending"]:
            entry = {"id": f"def_{int(time.time())}_{len(data['deferred'])}", "after": ns.after,
                     "opts": vars(o), "spec": spec}
            data["deferred"].append(entry)
            save_run(data)
            emit(ns, entry, [], [f"defer  {o.title}  starts when {', '.join(state['pending'])} complete(s); "
                                 f"`orcw wait` launches it"])
            return EXIT_OK
        bodies = state["bodies"]
    return start_task(ns, run, data, o, spec, bodies)


def launch_deferred(ns: argparse.Namespace, run: str, data: Dict[str, Any]) -> List[str]:
    """Start every deferred task whose upstreams have all completed."""
    lines: List[str] = []
    if not data["deferred"]:
        return lines
    keep = []
    for entry in data["deferred"]:
        try:
            state = upstream_state(run, entry["after"])
        except Refused as exc:
            lines.append(f"defer  dropped {entry['opts'].get('title')}: {exc}")
            continue
        if state["pending"]:
            keep.append(entry)
            continue
        o = SimpleNamespace(**entry["opts"])
        lines.append(f"start  deferred {o.title} (after {', '.join(entry['after'])})")
        try:
            code = start_task(ns, run, data, o, entry["spec"], state["bodies"], collect=lines)
            if code != EXIT_OK:
                lines.append(f"defer  {o.title}: worker not started; see error above")
        except (OrcaError, Refused) as exc:
            if isinstance(exc, OrcaError):
                exc.report()
            lines.append(f"defer  dropped {o.title}: {exc}; recreate it with `orcw task`")
        data = load_run(run)
    data["deferred"] = keep
    save_run(data)
    return lines


def cmd_tell(ns: argparse.Namespace) -> int:
    dispatch = resolve_dispatch(ns, ns.target)
    subject = ns.subject or trunc(ns.text, 60)
    docs = orca("orchestration", "send", "--to", f"dispatch:{dispatch}", "--type", "status",
                "--subject", subject, "--body", ns.text)
    view = project(result(docs), "send")
    view["dispatch"] = dispatch
    emit(ns, view, docs, [f"sent   {view['message']}  -> dispatch:{dispatch}  | {trunc(subject, 70)}"])
    return EXIT_OK


def live_workers(run: str) -> List[Dict[str, Any]]:
    res = result(orca("orchestration", "worker-list", "--run", run))
    return [w for w in res.get("workers") or [] if w.get("dispatchStatus") not in SETTLED]


def agent_wait(dispatch: str) -> Any:
    try:
        return project(result(orca("orchestration", "worker-show", "--dispatch", dispatch)), "worker")["agentWait"]
    except OrcaError:
        return None


def settle_delivery(ns: argparse.Namespace, run: str, data: Dict[str, Any], delivery: str,
                    messages: List[Dict[str, Any]], reuse: Dict[str, str]) -> List[str]:
    """Release or reuse every accepted worker_done in a delivery, then ack it. Caller has checked questions."""
    lines: List[str] = []
    actions: List[Dict[str, Any]] = []
    for msg in messages:
        mv = message_view(msg)
        if mv["type"] != "worker_done" or not mv["dispatch"]:
            continue
        if mv["rejected"]:
            lines.append(f"skip   {mv['task']}  rejected worker_done; worker still live, nothing released")
            actions.append({"task": mv["task"], "action": "skipped_rejected"})
            continue
        task_id, dispatch = mv["task"], mv["dispatch"]
        rec = data["tasks"].setdefault(task_id or dispatch, {})
        rec["status"] = mv["outcome"] or "completed"
        if task_id in reuse:
            handle = rec.get("handle") or project(
                result(orca("orchestration", "worker-show", "--dispatch", dispatch)), "worker")["handle"]
            if not handle:
                raise Refused(f"--reuse {task_id}: no agent terminal handle known for {dispatch}")
            receipt = project(result(orca("orchestration", "worker-start", "--task", reuse[task_id],
                                          "--run", run, "--terminal", handle)), "worker_start")
            data["tasks"].setdefault(reuse[task_id], {}).update(
                {"dispatch": receipt["dispatch"], "handle": receipt["handle"] or handle, "path": rec.get("path"),
                 "branch": rec.get("branch"), "worktree": rec.get("worktree"), "supervised": True,
                 "status": "dispatched"})
            actions.append({"task": task_id, "action": "reused", "next": reuse[task_id], "dispatch": receipt["dispatch"]})
            lines.append(f"reuse  {task_id} -> {reuse[task_id]}  dispatch {receipt['dispatch']}  agent {handle}")
            continue
        rel = project(result(orca("orchestration", "worker-release", "--dispatch", dispatch)), "release")
        state = str(rel["state"] or "released")
        reason = rel["reason"]
        if state == "retained":
            for w in result(orca("orchestration", "worker-list", "--run", run)).get("workers") or []:
                if w.get("dispatchId") == dispatch:
                    reason = get(w, "resource.retainedReason") or reason
        actions.append({"task": task_id, "action": "released", "state": state, "reason": reason})
        line = f"free   {task_id}  {state}" + (f" ({reason})" if state == "retained" and reason else "")
        if state == "retained":
            own = os.path.realpath(git(os.getcwd(), "rev-parse", "--show-toplevel") or "/nonexistent")
            wt, path = rec.get("worktree"), rec.get("path")
            if reason == "user_takeover":
                line += "; a user took this terminal over, so Orca leaves it open; close the tab by hand if unwanted"
            elif reason and "no_owned_resource" in str(reason) and wt and path and os.path.realpath(path) != own:
                line += f"; unsupervised worker, remove its worktree with `orca worktree rm --worktree id:{wt} --json`"
            elif reason and "no_owned_resource" in str(reason):
                line += "; unsupervised worker in the coordinator's worktree, close its terminal tab by hand"
        lines.append(line)
    orca("orchestration", "check", "--run", run, "--ack", delivery)
    data["delivery"] = None
    save_run(data)
    log_event("done", {"delivery": delivery, "actions": actions})
    lines.append(f"acked  {delivery}")
    return lines


def open_questions(data: Dict[str, Any], messages: List[Dict[str, Any]]) -> List[str]:
    return [message_view(m)["id"] for m in messages
            if message_view(m)["type"] == "question" and message_view(m)["id"] not in data["replied"]]


def all_settled(run: str, data: Dict[str, Any]) -> bool:
    return not live_workers(run) and not data["deferred"]


def cmd_wait(ns: argparse.Namespace) -> int:
    if ns.auto:
        return auto_wait(ns)
    return wait_once(ns)


def auto_wait(ns: argparse.Namespace) -> int:
    """Keep waiting; release and ack deliveries that need no decision; stop on a question or when all settle."""
    run = require_run(ns)
    deadline = time.time() + duration(ns.budget)
    rounds = 0
    acked: List[str] = []
    while True:
        data = load_run(run)
        settled = all_settled(run, data)
        if time.time() > deadline and not settled:
            print(f"budget   {ns.budget} elapsed with workers still live; rerun `orcw wait --auto` to keep going")
            return EXIT_OK
        rounds += 1
        timeout_ms = duration(ns.timeout) * 1000
        # Nothing live: drain any unacked delivery without blocking, then stop.
        args = ["orchestration", "check", "--run", run] if settled else \
            ["orchestration", "check", "--run", run, "--wait", "--types", ns.types, "--timeout-ms", str(timeout_ms)]
        docs = orca(*args, timeout=timeout_ms / 1000 + 30)
        res = result(docs)
        delivery = project(res, "delivery")["delivery"]
        messages = res.get("messages") or []
        if not messages and settled:
            print(f"settled  every task in {run} is finished and released" + (f" after {rounds - 1} wait(s)" if rounds > 1 else ""))
            return EXIT_OK
        if not messages:
            print(f"quiet  no messages in {ns.timeout}; still waiting")
            for line in status_lines(status_rows(run, data)):
                print(line)
            continue
        if delivery in acked:
            print(f"stuck  Orca returned {delivery} again after it was acknowledged; stopping so nothing loops. "
                  f"Inspect with `orcw resume`")
            return EXIT_ORCA
        print(f"deliv  {delivery}  {len(messages)} message(s)")
        for msg in messages:
            for line in message_lines(run, msg, ns.full):
                print(line)
            mv = message_view(msg)
            if mv["type"] == "worker_done" and not mv["rejected"] and mv["task"] in data["tasks"]:
                data["tasks"][mv["task"]]["status"] = mv["outcome"] or "completed"
            if mv["type"] == "question" and mv["id"] not in data["replied"]:
                data["questions"][mv["id"]] = mv["task"] or mv["from"]
        data["delivery"] = delivery
        save_run(data)
        log_event("delivery", {"delivery": delivery, "messages": [message_view(m) for m in messages]})
        qs = open_questions(data, messages)
        if qs:
            print(f"stop   {len(qs)} question(s) need you: " + ", ".join(qs))
            print(f"next   `orcw reply <id> \"<answer>\"` each, then `orcw done {delivery}` or `orcw wait --auto`")
            return EXIT_OK
        for line in settle_delivery(ns, run, data, delivery, messages, {}):
            print(line)
        acked.append(delivery)
        data = load_run(run)
        for line in launch_deferred(ns, run, data):
            print(line)


def wait_once(ns: argparse.Namespace) -> int:
    run = require_run(ns)
    data = load_run(run)
    timeout_ms = duration(ns.timeout) * 1000
    args = ["orchestration", "check", "--run", run, "--wait", "--types", ns.types, "--timeout-ms", str(timeout_ms)]
    if ns.ack:
        args += ["--ack", ns.ack]
    docs = orca(*args, timeout=timeout_ms / 1000 + 30)
    res = result(docs)
    view = project(res, "delivery")
    messages = res.get("messages") or []
    view["messages"] = [message_view(m) for m in messages]
    lines: List[str] = []
    if not messages:
        live = live_workers(run)
        lines.append(f"quiet  no messages in {ns.timeout}; {len(live)} worker(s) live; this is a checkpoint, not a failure")
        lines += status_lines(status_rows(run, data))
        if data["deferred"]:
            lines.append(f"defer  {len(data['deferred'])} task(s) waiting on upstream completion")
        emit(ns, view, docs, lines)
        return EXIT_OK
    lines.append(f"deliv  {view['delivery']}  {len(messages)} message(s); `orcw done {view['delivery']}` after handling all")
    for msg in messages:
        lines += message_lines(run, msg, ns.full)
        mv = message_view(msg)
        if mv["type"] == "worker_done" and not mv["rejected"] and mv["task"] in data["tasks"]:
            data["tasks"][mv["task"]]["status"] = mv["outcome"] or "completed"
        if mv["type"] == "question" and mv["id"] not in data["replied"]:
            data["questions"][mv["id"]] = mv["task"] or mv["from"]
    data["delivery"] = view["delivery"]
    save_run(data)
    log_event("delivery", {"delivery": view["delivery"], "messages": view["messages"]})
    lines += launch_deferred(ns, run, data)
    emit(ns, view, docs, lines)
    return EXIT_OK


def cmd_reply(ns: argparse.Namespace) -> int:
    run = require_run(ns)
    docs = orca("orchestration", "reply", "--id", ns.message, "--body", ns.text)
    data = load_run(run)
    if ns.message not in data["replied"]:
        data["replied"].append(ns.message)
    data["questions"].pop(ns.message, None)
    save_run(data)
    emit(ns, {"message": ns.message, "replied": True}, docs, [f"reply  {ns.message}  | {trunc(ns.text, 90)}"])
    return EXIT_OK


def cmd_done(ns: argparse.Namespace) -> int:
    run = require_run(ns)
    data = load_run(run)
    docs = orca("orchestration", "check", "--run", run)
    res = result(docs)
    delivery = project(res, "delivery")["delivery"]
    if delivery and delivery != ns.delivery:
        raise Refused(f"oldest unacked delivery is {delivery}, not {ns.delivery}; run `orcw wait` and handle it first")
    messages = res.get("messages") or []
    open_qs = open_questions(data, messages)
    if open_qs:
        raise Refused("unanswered question(s): " + ", ".join(open_qs) + "; `orcw reply <id> \"<answer>\"` first")
    if any("=" not in pair for pair in ns.reuse):
        raise Refused("--reuse expects TASK=NEXT_TASK")
    reuse = dict(pair.split("=", 1) for pair in ns.reuse)
    lines = settle_delivery(ns, run, data, ns.delivery, messages, reuse)
    emit(ns, {"delivery": ns.delivery, "lines": lines}, docs, lines)
    return EXIT_OK


def cmd_log(ns: argparse.Namespace) -> int:
    run = require_run(ns)
    path = home() / "runs" / run / "log.jsonl"
    if not path.exists():
        raise Refused(f"no log for {run} yet")
    needle = ns.task
    lines: List[str] = []
    for raw in path.read_text().splitlines():
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if entry.get("kind") == "orca" and not ns.calls:
            continue
        if needle and needle not in raw:
            continue
        kind = entry.get("kind")
        if kind == "orca":
            detail = " ".join(str(a) for a in entry.get("args", []) if not str(a).startswith("--json"))[:COLS - 30]
        elif kind == "delivery":
            detail = f"{entry.get('delivery')}: " + "; ".join(
                f"{m.get('type')} {m.get('task') or ''} {trunc(m.get('subject'), 40)}".strip() for m in entry.get("messages", []))
        elif kind == "done":
            detail = f"{entry.get('delivery')}: " + "; ".join(
                f"{a.get('action')} {a.get('task') or ''} {a.get('state') or ''}".strip() for a in entry.get("actions", []))
        elif kind == "task":
            detail = f"{entry.get('task')} dispatch {entry.get('dispatch')} at {tilde(entry.get('path'))}"
        else:
            detail = json.dumps({k: v for k, v in entry.items() if k not in ("t", "kind")})
        lines.append(cut(f"{entry.get('t', '')}  {kind:<9} {detail}"))
    emit(ns, {"run": run, "entries": len(lines)}, [], lines or ["nothing logged" + (f" for {needle}" if needle else "")])
    return EXIT_OK


def cmd_request(ns: argparse.Namespace) -> int:
    docs = orca("orchestration", "request-show", "--request", ns.request)
    res = result(docs)
    view = {"request": get(res, "requestId", default=ns.request), "state": get(res, "state"),
            "interpretation": get(res, "interpretation")}
    hint = {
        "completed": "it landed; replaying the same command with --retry-request would only return the recorded outcome",
        "pending": "still running or unrecorded; wait, then `orcw status --rebuild`",
        "absent": "no receipt here; not proof nothing happened, inspect `orcw status --rebuild` before retrying",
    }.get(str(view["state"]), "")
    emit(ns, view, docs, [f"req    {view['request']}  {view['state']}  {hint}".rstrip(),
                          "       " + trunc(view["interpretation"], COLS - 7)])
    return EXIT_OK


def cmd_read(ns: argparse.Namespace) -> int:
    run = require_run(ns)
    data = load_run(run)
    dispatch = resolve_dispatch(ns, ns.target)
    args = ["orchestration", "worker-read", "--dispatch", dispatch, "--limit", str(ns.limit)]
    if ns.source != "auto":
        args += ["--source", ns.source]
    cursor = None if (ns.restart or ns.source != "auto") else data["cursors"].get(dispatch)
    if cursor:
        args += ["--cursor", cursor]
    docs = orca(*args)
    res = result(docs)
    view = project(res, "read")
    rows = view["rows"] or []
    if view["cursor"]:
        data["cursors"][dispatch] = view["cursor"]
        save_run(data)
    lines = [f"read   {dispatch}  source {view['source']}  worker {view['worker']}  terminal {view['terminal']}  {len(rows)} row(s)"]
    for w in view["warnings"] or []:
        lines.append(f"note   {trunc(w, COLS - 7)}")
    for row in rows:
        text = row if isinstance(row, str) else (get(row, "output", "text", "line", "content") or json.dumps(row))
        for ln in str(text).splitlines() or [""]:
            lines.append("    " + cut(ln, COLS - 4))
    emit(ns, view, docs, lines)
    return EXIT_OK


def rebuild(run: str, data: Dict[str, Any]) -> Dict[str, Any]:
    workers = {w.get("taskId"): w for w in result(orca("orchestration", "worker-list", "--run", run)).get("workers") or []}
    terms = {t.get("handle"): t for t in result(orca("terminal", "list")).get("terminals") or []}
    for row in task_rows(run):
        task_id = row.get("id")
        rec = data["tasks"].setdefault(task_id, {})
        rec["status"] = row.get("status")
        rec.setdefault("title", row.get("task_title"))
        w = workers.get(task_id)
        if w:
            rec["dispatch"] = w.get("dispatchId") or rec.get("dispatch")
            rec["handle"] = w.get("agentTerminalHandle") or rec.get("handle")
            rec["supervised"] = w.get("workerState") != "unsupervised"
            rec["terminal_state"] = w.get("terminalState")
        t = terms.get(rec.get("handle"))
        if t:
            rec["path"] = t.get("worktreePath") or rec.get("path")
            rec["worktree"] = t.get("worktreeId") or rec.get("worktree")
            rec["branch"] = strip_ref(t.get("branch")) or rec.get("branch")
    save_run(data)
    return data


def status_rows(run: str, data: Dict[str, Any], with_git: bool = True) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        for w in result(orca("orchestration", "worker-list", "--run", run)).get("workers") or []:
            rec = data["tasks"].get(w.get("taskId"))
            if rec is not None:
                rec["terminal_state"] = w.get("terminalState")
                if w.get("dispatchStatus") in SETTLED and rec.get("status") not in ("succeeded", "failed"):
                    rec["status"] = w.get("dispatchStatus")
        save_run(data)
    except OrcaError:
        pass
    for task_id, rec in sorted(data["tasks"].items()):
        row = {"task": task_id, "status": rec.get("status"), "terminal_state": rec.get("terminal_state"),
               "path": rec.get("path"), "branch": rec.get("branch"), "dirty": None, "unpushed": None, "pr": None,
               "title": rec.get("title"), "agentWait": None, "worktree": rec.get("worktree")}
        path = rec.get("path")
        if with_git and path and os.path.isdir(path):
            row["dirty"] = len(git(path, "status", "--porcelain").splitlines())
            ahead = git(path, "rev-list", "--count", "@{u}..HEAD")
            if not ahead.isdigit():
                base = git(path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") or "origin/main"
                ahead = git(path, "rev-list", "--count", f"{base}..HEAD")
            row["unpushed"] = int(ahead) if ahead.isdigit() else "no-upstream"
            if rec.get("branch") and shutil_which("gh"):
                pr = subprocess.run(["gh", "pr", "list", "--head", rec["branch"], "--state", "all", "--limit", "1",
                                     "--json", "number,state,url"], cwd=path, capture_output=True, text=True)
                try:
                    found = json.loads(pr.stdout or "[]")
                except ValueError:
                    found = []
                if found:
                    row["pr"] = f"#{found[0].get('number')} {found[0].get('state', '').lower()}"
        if rec.get("dispatch") and row["status"] not in SETTLED:
            row["agentWait"] = agent_wait(rec["dispatch"])
        row["questions"] = [q for q, t in data.get("questions", {}).items() if t == task_id]
        rows.append(row)
    return rows


def shutil_which(name: str) -> Optional[str]:
    from shutil import which
    return which(name)


def status_lines(rows: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for r in rows:
        flags = []
        if r["dirty"]:
            flags.append(f"dirty {r['dirty']}")
        if r["unpushed"] not in (None, 0):
            flags.append(f"unpushed {r['unpushed']}")
        if r["pr"]:
            flags.append(r["pr"])
        if r["agentWait"]:
            flags.append("WAITING ON HUMAN")
        if r.get("questions"):
            flags.append(f"QUESTIONS {len(r['questions'])}: {' '.join(r['questions'])}")
        term = f" {r['terminal_state']:<10}" if r["terminal_state"] else ""
        flag_text = f"  [{'; '.join(flags)}]" if flags else ""
        lines.append(cut(f"{r['task']}  {str(r['status']):<10}{term}{flag_text}  {r['branch'] or '?'}  "
                         f"{tilde(r['path'])}".rstrip()))
    return lines or ["no tasks recorded for this run"]


def cmd_status(ns: argparse.Namespace) -> int:
    run = require_run(ns)
    data = load_run(run)
    if ns.rebuild or not data["tasks"]:
        data = rebuild(run, data)
    rows = status_rows(run, data)
    emit(ns, {"run": run, "tasks": rows}, [], [f"run    {run}  | {trunc(data.get('objective', ''), 90)}"] + status_lines(rows))
    return EXIT_OK


def cmd_resume(ns: argparse.Namespace) -> int:
    run = require_run(ns)
    data = rebuild(run, load_run(run))
    rows = status_rows(run, data)
    lines = [f"run    {run}  | {trunc(data.get('objective', ''), 90)}"] + status_lines(rows)
    pending = orca("orchestration", "check", "--run", run, allow_fail=True)
    res = result(pending)
    messages = res.get("messages") or []
    delivery = project(res, "delivery")["delivery"]
    if messages:
        lines.append(f"deliv  {delivery}  {len(messages)} unacked message(s):")
        for msg in messages:
            lines += message_lines(run, msg, ns.full)
        open_qs = open_questions(data, messages)
        if open_qs:
            lines.append("open   questions: " + ", ".join(open_qs))
        lines.append(f"next   reply to open questions, then `orcw done {delivery}`")
    else:
        lines.append("deliv  nothing unacked; `orcw wait` to continue")
    data["delivery"] = delivery
    save_run(data)
    emit(ns, {"run": run, "tasks": rows, "delivery": delivery, "messages": [message_view(m) for m in messages]}, pending, lines)
    return EXIT_OK


def cmd_cleanup(ns: argparse.Namespace) -> int:
    run = require_run(ns)
    data = load_run(run)
    rows = status_rows(run, data)
    removed, kept = [], []
    for r in rows:
        why = []
        if r["status"] not in ("completed", "succeeded"):
            why.append(f"status {r['status']}")
        if r["dirty"]:
            why.append(f"{r['dirty']} dirty file(s)")
        if r["unpushed"] not in (None, 0):
            why.append(f"unpushed {r['unpushed']}")
        if r["pr"] and not any(s in r["pr"] for s in ("merged", "closed")):
            why.append(f"PR {r['pr']}")
        if not r["path"] or not os.path.isdir(r["path"]):
            why.append("no worktree path")
        elif os.path.realpath(r["path"]) == os.path.realpath(git(os.getcwd(), "rev-parse", "--show-toplevel") or "/nonexistent"):
            why.append("this is the coordinator's own worktree")
        elif (worktree_by_path(r["path"]) or {}).get("isMainWorktree"):
            why.append("main worktree of the repo")
        if why:
            kept.append({"task": r["task"], "path": r["path"], "why": why})
            continue
        wt = r["worktree"] or (worktree_by_path(r["path"]) or {}).get("id")
        if not wt:
            kept.append({"task": r["task"], "path": r["path"], "why": ["worktree id unknown; `orcw status --rebuild`"]})
            continue
        if ns.apply:
            orca("worktree", "rm", "--worktree", f"id:{wt}")
        removed.append({"task": r["task"], "path": r["path"], "worktree": wt})
    lines = [f"{'rm     ' if ns.apply else 'would  '}{x['task']}  {x['path']}" for x in removed]
    lines += [f"keep   {x['task']}  {x['path']}  ({'; '.join(x['why'])})" for x in kept]
    if not ns.apply and removed:
        lines.append("dry run; add --apply to remove")
    emit(ns, {"removed": removed, "kept": kept, "applied": ns.apply}, [], lines or ["nothing to clean"])
    return EXIT_OK


def cmd_handoff(ns: argparse.Namespace) -> int:
    ensure_doctor()
    spec = read_spec(ns.spec)
    lint_spec(spec)
    subs = {"branch": "(set by Orca at create)", "path": "(this worktree)", "repo": ns.repo or "", "run": "",
            "base_commit": ns.base or "(repo default base)", "name": ns.name}
    text = render_spec(spec, "handoff", subs, ns.context, ns.commit_policy, None)
    wt = create_worktree(ns, agent=ns.agent, prompt=text)
    view = {k: wt.get(k) for k in ("worktree", "path", "branch", "base_commit", "handle")}
    lines = [
        f"handed {wt.get('path')}  branch {wt.get('branch')}  base {str(wt.get('base_commit'))[:12]}",
        f"agent  {wt.get('handle')}  ({ns.agent}); no Run, no Task, not monitored",
    ]
    emit(ns, view, wt.get("raw", []), lines)
    return EXIT_OK


def cmd_spec(ns: argparse.Namespace) -> int:
    spec = read_spec(ns.file)
    for w in lint_spec(spec):
        print(f"warn   {w}", file=sys.stderr)
    subs = {"branch": ns.branch or "<branch>", "path": ns.path or "<path>", "repo": ns.repo or "",
            "run": current_run() or "<run>", "base_commit": ns.base or "<base>", "name": ns.name or "<name>"}
    print(render_spec(spec, "handoff" if ns.handoff else "task", subs, ns.context, ns.commit_policy, ns.report), end="")
    return EXIT_OK


# --------------------------------------------------------------------------- worker commands


def creds_path(task: str) -> Path:
    return home() / "workers" / f"{task}.json"


def load_creds(task: str) -> Dict[str, Any]:
    path = creds_path(task)
    creds = json.loads(path.read_text()) if path.exists() else {}
    if os.environ.get("ORCW_FROM"):
        creds["from"] = os.environ["ORCW_FROM"]
    if os.environ.get("ORCW_CAPABILITY"):
        creds["capability"] = os.environ["ORCW_CAPABILITY"]
    return creds


def store_inline_creds(ns: argparse.Namespace, task: str) -> None:
    """--from/--capability given on any worker verb are stored for later verbs."""
    inline = {k: v for k, v in (("from", getattr(ns, "from_handle", None)),
                                ("capability", getattr(ns, "capability", None))) if v}
    if not inline:
        return
    path = creds_path(task)
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = json.loads(path.read_text()) if path.exists() else {}
    stored.update(inline)
    path.write_text(json.dumps(stored) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def worker_send_args(ids: Dict[str, Any], need_capability: bool) -> List[str]:
    creds = load_creds(ids["task"])
    args: List[str] = []
    if creds.get("from"):
        args += ["--from", creds["from"]]
    if creds.get("capability"):
        args += ["--dispatch-capability", creds["capability"]]
    elif need_capability:
        raise Refused("no dispatch capability stored for this task; Orca rejects worker_done without it. "
                      "Run `orcw w init --from <handle> --capability <token>` with the values from your preamble")
    return args


PREAMBLE_RE = {
    "from": re.compile(r"--from\s+(\S+)"),
    "capability": re.compile(r"--dispatch-capability\s+(\S+)"),
    "task": re.compile(r"--task-id\s+(\S+)"),
    "dispatch": re.compile(r"--dispatch-id\s+(\S+)"),
}


def cmd_w_init(ns: argparse.Namespace) -> int:
    found: Dict[str, str] = {}
    if ns.preamble_file:
        text = read_spec(ns.preamble_file)
        for key, rx in PREAMBLE_RE.items():
            m = rx.search(text)
            if m:
                found[key] = m.group(1).strip("\"'\\")
    if ns.from_handle:
        found["from"] = ns.from_handle
    if ns.capability:
        found["capability"] = ns.capability
    if ns.task:
        found["task"] = ns.task
    if ns.dispatch:
        found["dispatch"] = ns.dispatch
    if not found.get("from") and not found.get("capability"):
        raise Refused("nothing to store: pass --preamble-file - and paste your preamble, "
                      "or --from <handle> --dispatch-capability <token>")
    if not found.get("task"):
        probe = argparse.Namespace(task=None, dispatch=found.get("dispatch"), run=None)
        found["task"] = _worker_ids(probe)["task"]
    path = creds_path(found["task"])
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = json.loads(path.read_text()) if path.exists() else {}
    stored.update({k: v for k, v in found.items() if k in ("from", "capability", "dispatch")})
    path.write_text(json.dumps(stored) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    dispatch = stored.get("dispatch")
    if not dispatch:
        try:
            dispatch = project(result(orca("orchestration", "dispatch-show", "--task", found["task"])), "dispatch")["dispatch"]
        except OrcaError:
            dispatch = None
    view = {"task": found["task"], "dispatch": dispatch, "from": stored.get("from"),
            "capability": "stored" if stored.get("capability") else None, "state_file": str(path)}
    emit(ns, view, [], [
        f"init   task {found['task']}  dispatch {dispatch or '?'}  from {view['from'] or '?'}  "
        f"capability {view['capability'] or 'MISSING'}",
        f"       stored in {tilde(path)}; later `orcw w` commands need no flags",
    ])
    return EXIT_OK


def cmd_w_heartbeat(ns: argparse.Namespace) -> int:
    ids = worker_ids(ns)
    args = ["orchestration", "send", "--type", "heartbeat", "--subject", "alive",
            "--task-id", ids["task"], "--dispatch-id", ids["dispatch"], "--phase", ns.phase]
    args += worker_send_args(ids, need_capability=False)
    docs = orca(*args)
    emit(ns, {"task": ids["task"], "phase": ns.phase}, docs, [f"beat   {ids['task']}  {ns.phase}"])
    return EXIT_OK


def worker_ids(ns: argparse.Namespace) -> Dict[str, Any]:
    ids = _worker_ids(ns)
    store_inline_creds(ns, ids["task"])
    return ids


def _worker_ids(ns: argparse.Namespace) -> Dict[str, Any]:
    task, dispatch, run = getattr(ns, "task", None), getattr(ns, "dispatch", None), getattr(ns, "run", None)
    if not task:
        top = git(os.getcwd(), "rev-parse", "--show-toplevel")
        real = os.path.realpath(top) if top else None
        hits = []
        for f in glob.glob(str(home() / "runs" / "*" / "tasks" / "*.json")):
            try:
                rec = json.loads(Path(f).read_text())
            except ValueError:
                continue
            if real and rec.get("path") and os.path.realpath(rec["path"]) == real:
                hits.append((os.path.getmtime(f), rec))
        hits.sort(key=lambda h: (h[0], h[1].get("task") or ""), reverse=True)
        done_states = SETTLED | {"succeeded", "failed"}
        live = [rec for _, rec in hits if rec.get("status") not in done_states and rec.get("dispatch")]
        # Several tasks can share one worktree; the cache may lag, so let Orca confirm which is active.
        for rec in live:
            try:
                shown = project(result(orca("orchestration", "dispatch-show", "--task", rec["task"])), "dispatch")
            except OrcaError:
                continue
            if str(shown["status"]) not in SETTLED:
                task, dispatch, run = rec.get("task"), shown["dispatch"] or rec.get("dispatch"), shown["run"] or rec.get("run")
                break
        if not task and hits:
            task, dispatch, run = hits[0][1].get("task"), hits[0][1].get("dispatch"), hits[0][1].get("run")
    if not task:
        raise Refused("cannot find this worktree in any orcw run; pass --task <id> (and --dispatch <id>), "
                      "or use the raw `orca orchestration send` form from your injected preamble")
    view = project(result(orca("orchestration", "dispatch-show", "--task", task)), "dispatch")
    if dispatch and view["dispatch"] and dispatch != view["dispatch"]:
        raise Refused(f"cached dispatch {dispatch} differs from Orca's {view['dispatch']}; the task was re-dispatched")
    dispatch = view["dispatch"] or dispatch
    if str(view["status"]) in SETTLED:
        raise Refused(f"dispatch {dispatch} for {task} is {view['status']}; this preamble is stale, do not report on it")
    return {"task": task, "dispatch": dispatch, "run": view["run"] or run, "status": view["status"]}


def cmd_w_ids(ns: argparse.Namespace) -> int:
    ids = worker_ids(ns)
    emit(ns, ids, [], [f"task   {ids['task']}  dispatch {ids['dispatch']}  run {ids['run']}  ({ids['status']})"])
    return EXIT_OK


def cmd_w_mail(ns: argparse.Namespace) -> int:
    args = ["orchestration", "check", "--peek"]
    try:
        creds = load_creds(worker_ids(ns)["task"])
        if creds.get("from"):
            args += ["--terminal", creds["from"]]
    except (Refused, OrcaError):
        pass
    docs = orca(*args)
    res = result(docs)
    messages = res.get("messages") or []
    lines = [f"mail   {len(messages)} unread message(s) for this terminal"]
    for msg in messages:
        lines += message_lines(None, msg, True)
    emit(ns, {"messages": [message_view(m) for m in messages]}, docs, lines)
    return EXIT_OK


def cmd_w_ask(ns: argparse.Namespace) -> int:
    timeout_ms = duration(ns.timeout) * 1000
    args = ["orchestration", "ask", "--question", ns.question, "--timeout-ms", str(timeout_ms)]
    if ns.options:
        args += ["--options", ns.options]
    args += worker_send_args(worker_ids(ns), need_capability=False)
    docs = orca(*args, timeout=timeout_ms / 1000 + 30, allow_fail=True)
    err = next((d.get("error") for d in docs if isinstance(d, dict) and d.get("ok") is False), None)
    if err:
        pending = get(err, "data.messageId", "data.message_id", "messageId")
        if not pending or "timeout" not in str(get(err, "code", default="")).lower():
            raise OrcaError(err, orca_cmd() + args)
        view = {"message": pending, "answer": None, "status": "pending"}
    else:
        view = project(result(docs), "ask")
    if view["answer"] is None and view["message"]:
        print(f"pend   {view['message']} unanswered after {ns.timeout}; resuming once", file=sys.stderr)
        docs = orca("orchestration", "ask", "--resume", view["message"], "--timeout-ms", str(timeout_ms),
                    timeout=timeout_ms / 1000 + 30, allow_fail=True)
        view = dict(view, **{k: v for k, v in project(result(docs), "ask").items() if v is not None})
    if view["answer"] is None:
        emit(ns, view, docs, [f"pend   {view['message']}  still unanswered; `orcw w ask --resume {view['message']}` later"])
        return EXIT_OK
    emit(ns, view, docs, [f"answer {view['message']}  | {trunc(view['answer'], 100)}"])
    return EXIT_OK


def cmd_w_resume(ns: argparse.Namespace) -> int:
    timeout_ms = duration(ns.timeout) * 1000
    args = ["orchestration", "ask", "--resume", ns.message, "--timeout-ms", str(timeout_ms)]
    args += worker_send_args(worker_ids(ns), need_capability=False)
    docs = orca(*args, timeout=timeout_ms / 1000 + 30)
    view = project(result(docs), "ask")
    emit(ns, view, docs, [f"answer {ns.message}  | {trunc(view['answer'], 100)}" if view["answer"] is not None
                          else f"pend   {ns.message}  still unanswered"])
    return EXIT_OK


def cmd_w_done(ns: argparse.Namespace) -> int:
    ids = worker_ids(ns)
    body = read_spec(ns.body) if ns.body else ""
    if not body.strip():
        raise Refused("--body <file|-> is required: what changed, what you found, what remains")
    outcome = "succeeded" if ns.ok else "failed"
    args = ["orchestration", "send", "--type", "worker_done", "--subject", ns.subject, "--body", body,
            "--task-id", ids["task"], "--dispatch-id", ids["dispatch"], "--outcome", outcome]
    args += worker_send_args(ids, need_capability=not ns.no_capability)
    if ns.files:
        args += ["--files-modified", ns.files]
    if ns.report:
        args += ["--report-path", ns.report]
    docs = orca(*args)
    view = project(result(docs), "send")
    view.update(ids)
    view["outcome"] = outcome
    emit(ns, view, docs, [f"done   {ids['task']}  {outcome}  message {view['message']}; now idle at the prompt"])
    return EXIT_OK


# --------------------------------------------------------------------------- CLI


def add_worker_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--task")
    p.add_argument("--dispatch")
    p.add_argument("--from", dest="from_handle", help="shared flag, see `orcw w --help`")
    p.add_argument("--dispatch-capability", "--capability", dest="capability", help="shared flag, see `orcw w --help`")
    add_common(p)


def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="projected JSON with a stable key set")
    p.add_argument("--raw", action="store_true", help="Orca's own JSON, untouched")
    p.add_argument("--run", help="run id (default: ~/.orcw/current)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="orcw",
        description="One CLI for an Orca orchestration run: coordinator loop, worker replies, inventory.",
        epilog=(
            "Loop: doctor -> run -> task... -> wait -> reply... -> done -> (wait...) -> status -> cleanup.\n"
            "task places workers in the current worktree unless --name creates one or --in names one.\n"
            "task --after <t> defers until <t> completes; `wait` launches deferred tasks itself.\n"
            "wait --auto runs the whole loop until a question needs you or everything is settled.\n"
            "ORCW_RECORD=<dir> saves every Orca response as a fixture file.\n"
            "Exit codes: 0 ok, 1 Orca error (printed whole), 2 refused by orcw, 3 doctor found a gap.\n"
            "A timeout is exit 1 with the request id when Orca printed one; `orcw request <id>` asks\n"
            "whether that mutation landed before you retry anything.\n"
            "Not wrapped (use `orca skills get orchestration`): gate-*, --on <environment>, worker-stop,\n"
            "worker-abandon, worker-retain, reset, legacy Runs.\n"
            "`orcw help projections` lists which Orca fields survive into --json output."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", metavar="<command>")

    p = sub.add_parser("doctor", help="check this Orca has every command and flag orcw uses")
    add_common(p)
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("run", help="create a Run and make it current")
    p.add_argument("objective")
    p.add_argument("--comment", action="store_true", help="also write the objective into this worktree's Orca comment")
    add_common(p)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("task", help="create a task and start its worker; default placement is the current worktree")
    p.add_argument("--spec", help="Markdown spec file, or - for stdin")
    p.add_argument("--existing", metavar="TASK", help="attach a worker to a task that has none (after a failed start)")
    p.add_argument("--in", dest="into", help="existing worktree selector or path (default: current)")
    p.add_argument("--name", help="create a new worktree with this name instead")
    p.add_argument("--repo", help="repo selector or name for --name (name:<x>, id:<x>, path:<x>)")
    p.add_argument("--base", help="base branch/ref for the new worktree (default: repo default base)")
    p.add_argument("--child", action="store_true", help="child lineage under the active worktree (default: top-level)")
    p.add_argument("--agent", default="claude", help="claude | codex | ... (default claude)")
    p.add_argument("--share", action="store_true",
                   help="allow a second live worker in the same worktree (they will see each other's edits)")
    p.add_argument("--model", help="EXPERIMENTAL, untested live: provider model id (needs the launch-preferences capability)")
    p.add_argument("--effort", help="EXPERIMENTAL: reasoning effort; requires --model")
    p.add_argument("--setup", default="run", choices=["run", "skip", "inherit"])
    p.add_argument("--after", action="append", default=[], metavar="TASK",
                   help="start only after this task completes (repeatable); its report is prepended to the spec. "
                        "If it is still running, the start is deferred and `orcw wait` launches it")
    p.add_argument("--deps", nargs="*", help="task ids to record as Orca --deps (readiness only)")
    p.add_argument("--context", nargs="*", default=[], help="files the worker must read first")
    p.add_argument("--commit-policy", default="commit", choices=sorted(POLICIES))
    p.add_argument("--report", help="what the worker_done body must contain")
    p.add_argument("--title", help="task title (default: first line of the spec)")
    add_common(p)
    p.set_defaults(fn=cmd_task)

    p = sub.add_parser("tell", help="send guidance to one worker (task id or dispatch id)")
    p.add_argument("target")
    p.add_argument("text")
    p.add_argument("--subject")
    add_common(p)
    p.set_defaults(fn=cmd_tell)

    p = sub.add_parser("wait", help="wait for worker_done/escalation/question; never acks unless --auto")
    p.add_argument("--auto", action="store_true",
                   help="keep waiting: release settled workers, ack, launch deferred tasks; stop on a question "
                        "or when every task is settled")
    p.add_argument("--budget", default="2h", help="--auto: total time before returning anyway")
    p.add_argument("--timeout", default="15m", help="per wait: 900, 900s, 15m, or 1h (default 15m)")
    p.add_argument("--types", default=WAIT_TYPES)
    p.add_argument("--ack", help="acknowledge this delivery first (same as `done` without releases)")
    p.add_argument("--full", action="store_true", help="print whole bodies")
    add_common(p)
    p.set_defaults(fn=cmd_wait)

    p = sub.add_parser("reply", help="answer a worker question")
    p.add_argument("message")
    p.add_argument("text")
    add_common(p)
    p.set_defaults(fn=cmd_reply)

    p = sub.add_parser("done", help="release (or --reuse) every settled worker in a delivery, then ack it")
    p.add_argument("delivery")
    p.add_argument("--reuse", action="append", default=[], metavar="TASK=NEXT_TASK",
                   help="hand the finished task's terminal to another task instead of releasing")
    add_common(p)
    p.set_defaults(fn=cmd_done)

    p = sub.add_parser("log", help="this run's timeline from ~/.orcw; filter by task id")
    p.add_argument("task", nargs="?")
    p.add_argument("--calls", action="store_true", help="include every raw orca call")
    add_common(p)
    p.set_defaults(fn=cmd_log)

    p = sub.add_parser("request", help="did a mutation whose response was lost take effect? (read-only)")
    p.add_argument("request", help="request id: the envelope `id` printed with an orcw timeout error")
    add_common(p)
    p.set_defaults(fn=cmd_request)

    p = sub.add_parser("read", help="bounded worker output (transcript when Orca can prove it)")
    p.add_argument("target")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--restart", action="store_true", help="ignore the saved cursor")
    p.add_argument("--source", default="terminal", choices=["terminal", "transcript", "auto"],
                   help="terminal (default) = screen tail; transcript = hook-reported agent transcript, "
                        "which on 1.4.196 returned object keys instead of text")
    add_common(p)
    p.set_defaults(fn=cmd_read)

    p = sub.add_parser("status", help="one row per task: status, terminal, branch, path, dirty, unpushed, PR")
    p.add_argument("--rebuild", action="store_true", help="rebuild the cache from Orca first")
    add_common(p)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("resume", help="after context loss: status --rebuild plus the pending delivery")
    p.add_argument("--full", action="store_true")
    add_common(p)
    p.set_defaults(fn=cmd_resume)

    p = sub.add_parser("cleanup", help="remove worktrees of completed, clean, pushed, merged tasks (dry run)")
    p.add_argument("--apply", action="store_true", help="actually run `orca worktree rm`")
    add_common(p)
    p.set_defaults(fn=cmd_cleanup)

    p = sub.add_parser("handoff", help="give work to a new agent worktree; no Run, no Task, no monitoring")
    p.add_argument("--spec", required=True)
    p.add_argument("--repo")
    p.add_argument("--name", required=True)
    p.add_argument("--base")
    p.add_argument("--child", action="store_true")
    p.add_argument("--agent", default="claude")
    p.add_argument("--setup", default="run", choices=["run", "skip", "inherit"])
    p.add_argument("--context", nargs="*", default=[])
    p.add_argument("--commit-policy", default="pr", choices=sorted(POLICIES))
    add_common(p)
    p.set_defaults(fn=cmd_handoff)

    p = sub.add_parser("spec", help="render a spec file exactly as a worker would receive it")
    p.add_argument("file")
    p.add_argument("--repo")
    p.add_argument("--name")
    p.add_argument("--branch")
    p.add_argument("--path")
    p.add_argument("--base")
    p.add_argument("--handoff", action="store_true")
    p.add_argument("--context", nargs="*", default=[])
    p.add_argument("--commit-policy", default="commit", choices=sorted(POLICIES))
    p.add_argument("--report")
    p.set_defaults(fn=cmd_spec)

    w = sub.add_parser(
        "w", help="worker side: init, ids, mail, heartbeat, ask, resume, done",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Order: init once, then ids / heartbeat / mail / ask as needed, then done once and idle.\n"
            "\n"
            "Shared flags (every verb):\n"
            "  --task <id> --dispatch <id>      override the worktree-based lookup of your task\n"
            "  --from <handle>                  your terminal handle (the --from value in your preamble)\n"
            "  --dispatch-capability <token>    the token from your preamble; both are stored on first use\n"
            "  --json | --raw                   projected JSON, or Orca's own output\n"
            "Durations (--timeout): 600, 600s, 10m, or 1h."
        ),
    )
    ws = w.add_subparsers(dest="w_cmd", metavar="init|ids|mail|heartbeat|ask|resume|done")
    q = ws.add_parser("init", help="paste your preamble once: `w init --preamble-file - <<'P' ... P` (stores from + capability)")
    q.add_argument("--preamble-file", help="- for stdin (paste the preamble), or a file holding it; the two values are parsed out")
    q.add_argument("--from", dest="from_handle", help="alternative to --preamble-file: your --from handle")
    q.add_argument("--dispatch-capability", "--capability", dest="capability",
                   help="alternative to --preamble-file: your --dispatch-capability token")
    q.add_argument("--task")
    q.add_argument("--dispatch")
    add_common(q)
    q.set_defaults(fn=cmd_w_init)
    q = ws.add_parser("heartbeat", help="liveness signal the preamble asks for every 5 minutes")
    q.add_argument("phase", choices=["investigating", "implementing", "reviewing", "waiting"])
    add_worker_common(q)
    q.set_defaults(fn=cmd_w_heartbeat)
    q = ws.add_parser("ids", help="this worktree's task/dispatch/run; refuses if the dispatch is settled")
    add_worker_common(q)
    q.set_defaults(fn=cmd_w_ids)
    q = ws.add_parser("mail", help="unread coordinator messages for this terminal (peek, non-consuming)")
    add_worker_common(q)
    q.set_defaults(fn=cmd_w_mail)
    q = ws.add_parser("ask", help="block on a coordinator answer")
    q.add_argument("question")
    q.add_argument("--options", help="comma-separated")
    q.add_argument("--timeout", default="10m", help="how long to block: 600, 600s, 10m, or 1h (default 10m)")
    add_worker_common(q)
    q.set_defaults(fn=cmd_w_ask)
    q = ws.add_parser("resume", help="resume a pending question by message id")
    q.add_argument("message")
    q.add_argument("--timeout", default="10m", help="how long to block: 600, 600s, 10m, or 1h (default 10m)")
    add_worker_common(q)
    q.set_defaults(fn=cmd_w_resume)
    q = ws.add_parser("done", help="send worker_done once; --ok or --failed is required")
    g = q.add_mutually_exclusive_group(required=True)
    g.add_argument("--ok", action="store_true")
    g.add_argument("--failed", action="store_true")
    q.add_argument("subject")
    q.add_argument("--body", required=True, help="file or - for stdin")
    q.add_argument("--files", help="comma-separated changed files")
    q.add_argument("--report", help="report path")
    q.add_argument("--no-capability", action="store_true", help="send without a stored capability (Orca will likely reject)")
    add_worker_common(q)
    q.set_defaults(fn=cmd_w_done)
    w.set_defaults(fn=lambda ns: (w.print_help(), EXIT_OK)[1])

    p = sub.add_parser("help", help="help projections: which Orca fields survive into --json")
    p.add_argument("topic", nargs="?")
    p.set_defaults(fn=cmd_help)
    return ap


def cmd_help(ns: argparse.Namespace) -> int:
    if ns.topic == "projections":
        for name, spec in PROJECTIONS.items():
            print(name)
            for key, paths in spec.items():
                print(f"  {key:<15} <- {' | '.join(paths)}")
        return EXIT_OK
    build_parser().print_help()
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    try:  # long-running loops are read through pipes and log files; do not buffer their progress
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    ap = build_parser()
    ns = ap.parse_args(argv)
    if not getattr(ns, "fn", None):
        ap.print_help()
        return EXIT_OK
    try:
        return ns.fn(ns)
    except OrcaError as exc:
        exc.report()
        return EXIT_ORCA
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except DoctorFailed as exc:
        print(f"doctor: {exc}", file=sys.stderr)
        return EXIT_DOCTOR
    except KeyboardInterrupt:
        print("interrupted; nothing was acknowledged", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
