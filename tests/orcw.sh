#!/usr/bin/env bash

# Regression for bin/orcw + lib/orcw.py against a fake Orca 1.4.194. No live
# Orca is needed.

set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd -P)
TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-orcw-test.XXXXXX")
trap 'rm -rf "$TEST_ROOT"' EXIT

FAKE_BIN="$TEST_ROOT/bin"
WT="$TEST_ROOT/wt"
LOG="$TEST_ROOT/calls.log"
export ORCW_HOME="$TEST_ROOT/orcw"
# On Linux the adapter resolves orca-ide, never bare orca (the GNOME screen reader). Pin the fake.
export ORCA_CLI_COMMAND="$FAKE_BIN/orca"
# Whether orcw is on PATH varies by machine; pin what the trailer tells workers to run.
export ORCW_CMD="$REPO/bin/orcw"
export ORCW_HEARTBEAT_INTERVAL=0
export FAKE_LOG="$LOG" FAKE_WT="$WT"
export FAKE_WORKER_START=ok FAKE_CHECK=msgs FAKE_DISPATCH_STATUS=dispatched FAKE_HELP_MISSING="" FAKE_CREATE=ok FAKE_UPSTREAM=completed FAKE_WORKERS=""

mkdir -p "$FAKE_BIN" "$WT"
git -C "$WT" init -q
git -C "$WT" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init

# ---------------------------------------------------------------- fake orca
cat >"$FAKE_BIN/orca" <<'PY'
#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\n")
WT = os.environ["FAKE_WT"]
env = os.environ.get
missing = [f for f in env("FAKE_HELP_MISSING", "").split(",") if f]

def out(obj, code=0):
    print(json.dumps(obj)); sys.exit(code)

def ok(result): out({"id": "x", "ok": True, "result": result})

def err(code, message, **data):
    out({"id": "x", "ok": False, "error": {"code": code, "message": message, "data": data,
         "nextSteps": ["Using this same Orca CLI executable, run: skills get orchestration --full"],
         "nextCommandArgs": ["skills", "get", "orchestration", "--full"]}}, 1)

HELP = {
    "orchestration": {"run-create": "--objective", "run-current": "", "task-create": "--spec --task-title --display-name --deps --run",
        "task-list": "--status --ready --brief --run", "worker-start": "--task --on --worktree --agent --terminal --model --effort --run",
        "worker-show": "--dispatch", "worker-read": "--dispatch --source --cursor --limit", "worker-list": "--run",
        "worker-release": "--dispatch", "dispatch": "--task --to --run --inject", "dispatch-show": "--task",
        "check": "--terminal --run --ack --unread --peek --all --types --wait --timeout-ms",
        "send": "--subject --to --run --body --type --task-id --dispatch-id --outcome --files-modified --report-path",
        "reply": "--id --body", "ask": "--question --resume --options --timeout-ms", "request-show": "--request"},
    "worktree": {"create": "--name --repo --agent --prompt --setup --base-branch --no-parent", "list": "", "rm": "--worktree --force",
        "show": "--worktree", "set": "--worktree --comment"},
    "terminal": {"wait": "--terminal --for --timeout-ms", "list": "--worktree --limit"},
}
if "--help" in args:
    group = args[0]
    if len(args) == 2:
        print(f"orca {group}\n\nUsage: orca {group} <command> [options]\n\nCommands:")
        for c in HELP[group]:
            print(f"  {c:<18} desc")
        sys.exit(0)
    flags = " ".join(f for f in HELP[group][args[1]].split() if f not in missing)
    print(f"orca {group} {args[1]}\n\nUsage: orca {group} {args[1]} {flags} [--json]")
    sys.exit(0)

a = [x for x in args if x != "--json"]
def flag(name, default=None):
    return a[a.index(name) + 1] if name in a else default

if a[:1] == ["status"]:
    ok({"app": {"running": True}, "runtime": {"appVersion": "1.4.194",
        "capabilities": ["orchestration.contract.v1", "orchestration.worker-launch-preferences.v1"]}})
if a[:2] == ["orchestration", "run-current"]:
    err("run_required", "No Run is bound.")
if a[:2] == ["orchestration", "run-create"]:
    ok({"run": {"id": "run_test0001", "objective": flag("--objective")}})
if a[:2] == ["worktree", "set"]:
    ok({"updated": True})
if a[:2] == ["worktree", "show"]:
    ok({"worktree": {"id": "repo-1::" + WT, "path": WT, "branch": "refs/heads/main", "repoId": "repo-1", "isMainWorktree": True}})
if a[:2] == ["worktree", "create"]:
    if env("FAKE_CREATE") == "repo_missing":
        err("repo_not_found", "Repository selector did not resolve.")
    if env("FAKE_CREATE") == "lost":
        out({"id": "x", "ok": False, "error": {"code": "runtime_unavailable", "message": "The Orca runtime closed the connection before responding."}}, 1)
    res = {"worktree": {"id": "repo-1::" + WT, "path": WT, "branch": "refs/heads/user-x/" + flag("--name", "wt"), "repoId": "repo-1"}}
    if "--agent" in a:
        res["agentTerminalHandle"] = "term_agent1"
    ok(res)
if a[:2] == ["worktree", "list"]:
    ok({"worktrees": [{"id": "repo-1::" + WT, "path": WT, "displayName": "main", "isMainWorktree": True},
                      {"id": "repo-1::" + WT + "-lostwt", "path": WT + "-lostwt", "displayName": "lostwt", "branch": "refs/heads/user-x/lostwt"}]})
if a[:2] == ["worktree", "rm"]:
    ok({"removed": flag("--worktree")})
if a[:2] == ["terminal", "wait"]:
    ok({"state": "tui-idle"})
if a[:2] == ["terminal", "list"]:
    ok({"terminals": [{"handle": "term_agent1", "agentIdentity": "claude", "worktreePath": WT, "worktreeId": "repo-1::" + WT, "branch": "refs/heads/user-x/wt"}]})
if a[:2] == ["orchestration", "task-create"]:
    counter = os.path.join(os.environ["ORCW_HOME"], "fake-task-counter")
    n = int(open(counter).read()) + 1 if os.path.exists(counter) else 1
    open(counter, "w").write(str(n))
    with open(os.path.join(os.environ["ORCW_HOME"], f"fake-spec-{n}.md"), "w") as fh:
        fh.write(flag("--spec", ""))
    ok({"task": {"id": f"task_{n:04d}", "task_title": flag("--task-title")}})
if a[:2] == ["orchestration", "worker-start"]:
    if env("FAKE_WORKER_START") == "fail":
        err("selector_not_found", "Worktree selector did not resolve.", selector=flag("--worktree"))
    ok({"state": "ready", "dispatch": {"id": "ctx_0001"}, "worker": {"agent_terminal_handle": flag("--terminal", "term_agent1")},
        "launch": {"requested": {}, "effective": {}}})
if a[:2] == ["orchestration", "dispatch"]:
    ok({"dispatched": True})
if a[:2] == ["orchestration", "dispatch-show"]:
    ok({"dispatch": {"id": "ctx_0001", "run_id": "run_test0001", "task_id": flag("--task"),
        "status": env("FAKE_DISPATCH_STATUS"), "assignee_handle": "term_agent1", "depth": 1}})
if a[:2] == ["orchestration", "check"]:
    if "--ack" in a and "--wait" not in a:
        ok({"acknowledged": flag("--ack")})
    if "--peek" in a:
        ok({"messages": [{"id": "msg_c1", "type": "status", "subject": "pin the tag", "body": "use 0.12.238", "from_handle": "term_coord"}], "count": 1})
    if "--unread" in a:
        state = os.path.join(os.environ["ORCW_HOME"], "fake-mail-read")
        if os.path.exists(state):
            ok({"messages": [], "count": 0})
        open(state, "w").write("read\n")
        ok({"messages": [{"id": "msg_c1", "type": "status", "subject": "pin the tag", "body": "use 0.12.238", "from_handle": "term_coord"}], "count": 1})
    if "--wait" in a:
        sys.stderr.write(json.dumps({"_keepalive": True, "elapsedMs": 15000}) + "\n")
        sys.stderr.flush()
        if env("FAKE_CHECK") == "slow":
            time.sleep(2)
            ok({"deliveryId": None, "messages": [], "count": 0})
        print(json.dumps({"_keepalive": True, "elapsedMs": 30000}))
    if env("FAKE_CHECK") == "empty":
        ok({"deliveryId": None, "messages": [], "count": 0})
    if env("FAKE_CHECK") == "rejected":
        ok({"deliveryId": "dlv_0002", "count": 1, "messages": [{"id": "msg_x1", "run_id": "run_test0001", "type": "worker_done",
            "from_handle": "term_agent1", "subject": "Rejected worker_done: did stuff", "body": "Orca rejected this worker_done: capability missing.",
            "payload": json.dumps({"taskId": "task_0001", "dispatchId": "ctx_0001", "outcome": "succeeded"})}]})
    msgs = [{"id": "msg_d1", "run_id": "run_test0001", "type": "worker_done", "from_handle": "term_agent1",
             "subject": "Released 0.12.238", "body": "Created the release. " + "x" * 1600,
             "payload": json.dumps({"taskId": "task_0001", "dispatchId": "ctx_0001", "outcome": "succeeded", "filesModified": []})}]
    if env("FAKE_CHECK") == "question":
        msgs.append({"id": "msg_q1", "run_id": "run_test0001", "type": "question", "from_handle": "term_agent2",
                     "subject": "Pin by tag or SHA?", "body": "Tag or SHA?", "payload": json.dumps({"taskId": "task_0002", "dispatchId": "ctx_0002"})})
    ok({"deliveryId": "dlv_0001", "messages": msgs, "count": len(msgs)})
if a[:2] == ["orchestration", "worker-list"]:
    if env("FAKE_WORKERS") == "retained":
        ok({"workers": [{"dispatchId": "ctx_gone", "taskId": "task_gone", "runId": "run_test0001",
            "workerState": "succeeded", "dispatchStatus": "completed", "agentTerminalHandle": "term_gone",
            "terminalState": "retained", "resource": {"retainedReason": "user_takeover",
                "worktreeId": "repo-1::" + WT + "-gone"}}]})
    ok({"workers": [], "counts": {}})
if a[:2] == ["orchestration", "worker-show"]:
    ok({"dispatchId": flag("--dispatch"), "workerState": "unsupervised", "terminalState": "retained",
        "agentTerminalHandle": "term_agent1", "observation": {"agentWait": None}})
if a[:2] == ["orchestration", "worker-release"]:
    ok({"dispatchId": flag("--dispatch"), "terminalState": "retained", "reason": "no_owned_resource"})
if a[:2] == ["orchestration", "reply"]:
    ok({"message": {"id": "msg_r1", "thread_id": flag("--id")}})
if a[:2] == ["orchestration", "send"]:
    ok({"message": {"id": "msg_s1"}})
if a[:2] == ["orchestration", "request-show"]:
    ok({"requestId": flag("--request"), "state": "absent", "interpretation": "No receipt for request under this caller identity."})
if a[:2] == ["orchestration", "task-list"]:
    extra = []
    state = os.path.join(os.environ["ORCW_HOME"], "fake-task-counter")
    n = int(open(state).read()) if os.path.exists(state) else 0
    for i in range(1, n + 1):
        extra.append({"id": f"task_{i:04d}", "status": "dispatched", "task_title": f"t{i}", "deps": "[]", "result": None})
    ok({"runId": flag("--run"), "tasks": extra + [{"id": "task_up01", "status": env("FAKE_UPSTREAM"), "task_title": "Cut the release", "deps": "[]",
        "result": json.dumps({"provenance": "worker_report", "outcome": "succeeded", "subject": "Released 0.12.238",
                              "body": "Created GitHub release 0.12.238 targeting 7084d5e."})}], "count": 1})
err("unknown_command", "fake orca does not implement: " + " ".join(a))
PY
chmod +x "$FAKE_BIN/orca"

cat >"$FAKE_BIN/gh" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = pr ] && [ "${2:-}" = list ]; then
	if [ -n "${FAKE_PR_HEAD:-}" ]; then
		printf '[{"number":7,"state":"MERGED","url":"https://example.test/pr/7","headRefOid":"%s"}]\n' "$FAKE_PR_HEAD"
	else
		printf '[]\n'
	fi
	exit 0
fi
exit 1
SH
chmod +x "$FAKE_BIN/gh"

ORCW="$REPO/bin/orcw"
export PATH="$FAKE_BIN:$PATH"
: >"$LOG"

fail() { echo "FAIL: $*" >&2; exit 1; }
expect_exit() { # expect_exit <code> <cmd...>
	local want=$1; shift
	local got=0
	"$@" >"$TEST_ROOT/out" 2>"$TEST_ROOT/err" || got=$?
	[ "$got" = "$want" ] || { cat "$TEST_ROOT/out" "$TEST_ROOT/err" >&2; fail "$* exited $got, wanted $want"; }
}
out_has() { grep -q -- "$1" "$TEST_ROOT/out" || { cat "$TEST_ROOT/out" >&2; fail "stdout lacks: $1"; }; }
err_has() { grep -q -- "$1" "$TEST_ROOT/err" || { cat "$TEST_ROOT/err" >&2; fail "stderr lacks: $1"; }; }
log_has() { grep -q -- "$1" "$LOG" || { cat "$LOG" >&2; fail "orca was never called with: $1"; }; }
log_lacks() { ! grep -q -- "$1" "$LOG" || { cat "$LOG" >&2; fail "orca was called with: $1"; }; }

# ---------------------------------------------------------------- doctor
expect_exit 0 "$ORCW" doctor
out_has "ok        orchestration worker-start"
out_has "ok        orchestration request-show"
out_has "app 1.4.194"

FAKE_HELP_MISSING="--request" expect_exit 0 env ORCW_HOME="$TEST_ROOT/orcw-opt" "$ORCW" doctor
out_has "degraded  orchestration request-show    optional"

FAKE_HELP_MISSING="--task-title" expect_exit 3 env ORCW_HOME="$TEST_ROOT/orcw-missing" "$ORCW" doctor
out_has "missing   orchestration task-create"
out_has "flags --task-title"

# ---------------------------------------------------------------- errors pass through whole
expect_exit 2 "$ORCW" wait # no run yet
err_has "refused: no current run"

expect_exit 2 "$ORCW" task --spec /dev/null --name x --run run_fake
err_has "refused: spec is empty"

# ---------------------------------------------------------------- run
: >"$LOG"
expect_exit 0 "$ORCW" run "Ship the ECR change"
out_has "run    run_test0001"
[ "$(cat "$ORCW_HOME/current")" = "run_test0001" ] || fail "current run not recorded"
log_lacks '"worktree", "set"'
: >"$LOG"
expect_exit 0 "$ORCW" run "Ship the ECR change" --comment
log_has '"worktree", "set"'

# ---------------------------------------------------------------- task: new worktree, supervised
printf '# Cut the release\n\nBranch is {{branch}} in {{path}}.\n' >"$TEST_ROOT/spec.md"
: >"$LOG"
expect_exit 0 "$ORCW" task --spec "$TEST_ROOT/spec.md" --repo demo --name rel --report "release URL"
out_has "task   task_0001  dispatch ctx_0001  supervised"
out_has "branch user-x/rel"
log_has '"worktree", "create", "--name", "rel", "--setup", "run", "--repo", "name:demo", "--no-parent", "--agent", "claude"'
log_has '"worker-start", "--task", "task_0001", "--run", "run_test0001", "--worktree", "id:repo-1::'"$WT"'", "--terminal", "term_agent1"'
log_lacks '"--inject"'
grep -q "Branch is user-x/rel in $WT" "$ORCW_HOME/fake-spec-1.md" || fail "placeholders not substituted from the real worktree"
grep -q "w init --from <handle> --capability <token>" "$ORCW_HOME/fake-spec-1.md" || fail "trailer does not show the short init"
grep -q "Every \`orcw\` below means \`$REPO/bin/orcw\`" "$ORCW_HOME/fake-spec-1.md" || fail "trailer lacks the launcher path"
grep -q 'w done --ok|--failed --summary "<short status>" --report <file>' "$ORCW_HOME/fake-spec-1.md" || fail "trailer lacks separate completion inputs"
grep -q "release URL" "$ORCW_HOME/fake-spec-1.md" || fail "--report not in trailer"
[ -f "$ORCW_HOME/runs/run_test0001/tasks/task_0001.json" ] || fail "per-task cache file missing"

: >"$LOG"
FAKE_CREATE=repo_missing expect_exit 1 "$ORCW" task --spec "$TEST_ROOT/spec.md" --repo missing --name missing
err_has "orca repo add --path <checkout>"

# ---------------------------------------------------------------- task: default placement is the current worktree
: >"$LOG"
expect_exit 2 "$ORCW" task --spec "$TEST_ROOT/spec.md"
err_has "already has a live worker (task_0001)"
log_lacks '"task-create"'
: >"$LOG"
expect_exit 0 "$ORCW" task --spec "$TEST_ROOT/spec.md" --share
out_has "task   task_0002  dispatch ctx_0001  supervised"
out_has "note   sharing"
log_has '"worktree", "show", "--worktree", "current"'
log_has '"worker-start", "--task", "task_0002", "--run", "run_test0001", "--worktree", "current", "--agent", "claude"'
log_lacks '"worktree", "create"'
expect_exit 2 "$ORCW" task --spec "$TEST_ROOT/spec.md" --in current --name x
err_has "exclusive"

# ---------------------------------------------------------------- task: worker-start fails -> exit 1, task kept, --existing retries
: >"$LOG"
FAKE_WORKER_START=fail expect_exit 1 "$ORCW" task --spec "$TEST_ROOT/spec.md" --repo demo --name rel2 --share
err_has "selector_not_found"
err_has "orcw task --existing task_0003 --in <worktree>"
log_lacks '"--inject"'
grep -q '"status": "unassigned"' "$ORCW_HOME/runs/run_test0001/tasks/task_0003.json" || fail "unassigned task not recorded"
: >"$LOG"
expect_exit 0 "$ORCW" task --existing task_0003 --in current --share
out_has "task   task_0003  dispatch ctx_0001  supervised"
log_lacks '"task-create"'
log_has '"worker-start", "--task", "task_0003", "--run", "run_test0001", "--worktree", "current", "--agent", "claude"'

# ---------------------------------------------------------------- task: lost worktree-create response is recovered by name
: >"$LOG"
FAKE_CREATE=lost expect_exit 0 "$ORCW" task --spec "$TEST_ROOT/spec.md" --repo demo --name lostwt
out_has "note   worktree create: runtime_unavailable; worktree found by name afterwards"
out_has "task   task_0004  dispatch ctx_0001  supervised"
log_has '"terminal", "list", "--worktree", "id:repo-1::'"$WT"'-lostwt"'
log_has '"worker-start", "--task", "task_0004", "--run", "run_test0001", "--worktree", "id:repo-1::'"$WT"'-lostwt", "--terminal", "term_agent1"'

# ---------------------------------------------------------------- task --after: completed upstream is prepended now
: >"$LOG"
expect_exit 0 "$ORCW" task --spec "$TEST_ROOT/spec.md" --after task_up01 --share
grep -q "## Upstream result (task_up01)" "$ORCW_HOME/fake-spec-5.md" || fail "--after did not prepend a heading"
grep -q "Created GitHub release 0.12.238" "$ORCW_HOME/fake-spec-5.md" || fail "--after did not prepend the upstream body"
log_has '"--task-title", "Cut the release"'

# ---------------------------------------------------------------- task --after: pending upstream defers; wait launches it
: >"$LOG"
FAKE_UPSTREAM=dispatched expect_exit 0 "$ORCW" task --spec "$TEST_ROOT/spec.md" --after task_up01 --title "Deferred consumer" --share
out_has "defer  Deferred consumer  starts when task_up01 complete(s)"
log_lacks '"task-create"'
[ "$(jq '.deferred | length' "$ORCW_HOME/runs/run_test0001.json")" = "1" ] || fail "deferred entry not recorded"
: >"$LOG"
expect_exit 0 "$ORCW" wait --timeout 1m
out_has "start  deferred Deferred consumer (after task_up01)"
out_has "task   task_0006  dispatch ctx_0001  supervised"
log_has '"--task-title", "Deferred consumer"'
grep -q "## Upstream result (task_up01)" "$ORCW_HOME/fake-spec-6.md" || fail "deferred start did not prepend the upstream body"
[ "$(jq '.deferred | length' "$ORCW_HOME/runs/run_test0001.json")" = "0" ] || fail "deferred entry not cleared"

# ---------------------------------------------------------------- spec: unresolved placeholder refused
printf 'Spaced {{ branch }} placeholder.\n' >"$TEST_ROOT/spaced.md"
expect_exit 0 "$ORCW" spec "$TEST_ROOT/spaced.md" --branch b --path /p
out_has "Spaced b placeholder."
printf 'Use {{branch}} and {{nonsense}}.\n' >"$TEST_ROOT/bad.md"
expect_exit 2 "$ORCW" spec "$TEST_ROOT/bad.md"
err_has "unknown placeholders: {{nonsense}}"
expect_exit 0 "$ORCW" spec "$TEST_ROOT/spec.md" --branch b --path /p --handoff
out_has "full handoff"
! grep -q "orcw w done" "$TEST_ROOT/out" || fail "handoff trailer carries worker lifecycle text"

# ---------------------------------------------------------------- wait: stream parsing, truncation, empty delivery
expect_exit 0 "$ORCW" wait --timeout 1m
out_has "deliv  dlv_0001  1 message(s)"
out_has "done   task_0001  succeeded  | Released 0.12.238"
out_has "more chars; --full or"
[ -f "$ORCW_HOME/runs/run_test0001/messages/msg_d1.txt" ] || fail "long body not saved"
log_has '"check", "--run", "run_test0001", "--wait", "--types", "worker_done,escalation,question", "--timeout-ms", "60000"'

FAKE_CHECK=empty expect_exit 0 "$ORCW" wait --timeout 1m
out_has "quiet  no messages in 1m; 0 worker(s) live; this is a checkpoint, not a failure"
out_has "task_0001  succeeded"

FAKE_CHECK=slow "$ORCW" wait --timeout 1m >"$TEST_ROOT/slow-out" 2>"$TEST_ROOT/slow-err" &
slow_pid=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
	grep -q "wait   15s elapsed" "$TEST_ROOT/slow-err" 2>/dev/null && break
	sleep 0.1
done
grep -q "wait   15s elapsed" "$TEST_ROOT/slow-err" || fail "wait keepalive was not streamed"
FAKE_CHECK=slow expect_exit 2 "$ORCW" wait --timeout 1m
err_has "another orcw wait is already running"
wait "$slow_pid"

: >"$LOG"
FAKE_CHECK=rejected expect_exit 0 "$ORCW" wait --timeout 1m
out_has "REJECT task_0001  Orca refused this worker_done; the task is NOT settled"
FAKE_CHECK=rejected expect_exit 0 "$ORCW" "done" dlv_0002
out_has "skip   task_0001  rejected worker_done; worker still live, nothing released"
log_lacks '"worker-release"'
log_has '"--ack", "dlv_0002"'

# ---------------------------------------------------------------- status shows open questions; wait --auto stops on them
FAKE_CHECK=question expect_exit 0 "$ORCW" wait --timeout 1m
expect_exit 0 "$ORCW" status
out_has "QUESTIONS 1: msg_q1"
: >"$LOG"
FAKE_CHECK=question expect_exit 0 "$ORCW" wait --auto --timeout 1m
out_has "stop   1 question(s) need you: msg_q1"
log_lacks '"--ack"'

# ---------------------------------------------------------------- wait --auto: settles a decision-free delivery, then reports all settled
: >"$LOG"
# the fake replays dlv_0001 forever, which is exactly the ack-failure case the loop must not spin on
expect_exit 1 env ORCW_RECORD="$TEST_ROOT/rec" "$ORCW" wait --auto --timeout 1m
out_has "free   task_0001"
out_has "acked  dlv_0001"
out_has "stuck  Orca returned dlv_0001 again after it was acknowledged"
FAKE_CHECK=empty expect_exit 0 "$ORCW" wait --auto --timeout 1m
out_has "settled  every task in run_test0001 is finished and released"
log_has '"--ack", "dlv_0001"'
[ "$(find "$TEST_ROOT/rec" -name '*.json' | wc -l | tr -d ' ')" -ge 3 ] || fail "ORCW_RECORD wrote no fixtures"
grep -q '"args"' "$(find "$TEST_ROOT/rec" -name '*check*' | head -1)" || fail "fixture lacks args"

expect_exit 0 "$ORCW" log task_0001
out_has "delivery"
out_has "done"

# ---------------------------------------------------------------- done: refuses on open question, then releases + acks
: >"$LOG"
FAKE_CHECK=question expect_exit 2 "$ORCW" "done" dlv_0001
err_has "unanswered question(s): msg_q1"
log_lacks '"--ack"'

FAKE_CHECK=question expect_exit 0 "$ORCW" reply msg_q1 "Pin by tag"
: >"$LOG"
FAKE_CHECK=question expect_exit 0 "$ORCW" "done" dlv_0001
out_has "free   task_0001  retained (no_owned_resource); unsupervised worker, remove its worktree with \`orca worktree rm --worktree id:repo-1::$WT --json\`"
out_has "acked  dlv_0001"
log_has '"worker-release", "--dispatch", "ctx_0001"'
log_has '"check", "--run", "run_test0001", "--ack", "dlv_0001"'

expect_exit 2 "$ORCW" "done" dlv_9999
err_has "oldest unacked delivery is dlv_0001, not dlv_9999"
expect_exit 2 "$ORCW" "done" dlv_0001 --reuse task_0001
err_has "expects TASK=NEXT_TASK"

# ---------------------------------------------------------------- status + cleanup (dry run never removes)
expect_exit 0 "$ORCW" status
out_has "task_0001  succeeded"
out_has "user-x/rel"
FAKE_PR_HEAD=$(git -C "$WT" rev-parse HEAD) expect_exit 0 "$ORCW" status --json
[ "$(jq -r '.tasks[] | select(.task == "task_0001") | .unpushed' "$TEST_ROOT/out")" = "0" ] ||
	fail "matching PR head was not recognized as pushed"

run_cache="$ORCW_HOME/runs/run_test0001.json"
jq --arg path "$WT-gone" '.tasks.task_gone = {
  "status": "succeeded", "title": "gone", "path": $path,
  "branch": "user-x/gone", "worktree": ("repo-1::" + $path), "dispatch": "ctx_gone"
} | .tasks.task_released = {
  "status": "succeeded", "title": "released", "path": ($path + "-released"),
  "branch": "user-x/released", "worktree": ("repo-1::" + $path + "-released"),
  "dispatch": "ctx_released", "terminal_state": "released"
}' "$run_cache" >"$TEST_ROOT/run.json"
mv "$TEST_ROOT/run.json" "$run_cache"
FAKE_WORKERS=retained expect_exit 0 "$ORCW" status
out_has "task_gone  succeeded  gone"
: >"$LOG"
FAKE_WORKERS=retained expect_exit 0 "$ORCW" cleanup
out_has "gone   task_gone"
out_has "gone   task_released"
log_lacks '"worktree", "rm"'

# ---------------------------------------------------------------- worker side
expect_exit 0 env -C "$WT" "$ORCW" w ids
out_has "dispatch ctx_0001  run run_test0001  (dispatched)"

FAKE_DISPATCH_STATUS=completed expect_exit 2 env -C "$WT" "$ORCW" w ids
err_has "this preamble is stale"

printf 'Did the thing.\n' >"$TEST_ROOT/report.md"
expect_exit 2 env -C "$WT" "$ORCW" w "done" --ok "Done" --body "$TEST_ROOT/report.md"
err_has "no dispatch capability stored"

cat >"$TEST_ROOT/preamble.txt" <<'EOF'
  orca orchestration send --from term_agent1 \
    --type worker_done --subject "<short status>" \
    --task-id task_0006 --dispatch-id ctx_0001 --outcome succeeded \
    --dispatch-capability cap_secret_123
EOF
expect_exit 0 env -C "$WT" "$ORCW" w init --preamble-file "$TEST_ROOT/preamble.txt"
out_has "init   task task_0006  dispatch ctx_0001  from term_agent1  capability stored"
out_has "later \`orcw w\` commands need no flags"
# the advertised form: paste the preamble on stdin
"$ORCW" w init --preamble-file - --task task_0005 >"$TEST_ROOT/out" 2>"$TEST_ROOT/err" <<'EOF' || fail "stdin init exited $?"
You are working inside Orca. Your coordinator's terminal handle is: term_coord
  orca orchestration send --from term_agent1 \
    --task-id task_0005 --dispatch-id ctx_0001 --outcome succeeded \
    --dispatch-capability cap_from_stdin
=== TASK ===
EOF
out_has "init   task task_0005  dispatch ctx_0001  from term_agent1  capability stored"
grep -q cap_from_stdin "$ORCW_HOME/workers/task_0005.json" || fail "stdin preamble not parsed"

: >"$LOG"
expect_exit 0 env -C "$WT" "$ORCW" w heartbeat implementing
log_has '"--type", "heartbeat", "--subject", "alive", "--task-id", "task_0006", "--dispatch-id", "ctx_0001", "--phase", "implementing", "--from", "term_agent1", "--dispatch-capability", "cap_secret_123"'

: >"$LOG"
ORCW_HEARTBEAT_INTERVAL=0.1 expect_exit 0 env -C "$WT" "$ORCW" w init --from term_agent1 --capability cap_secret_123
for _ in 1 2 3 4 5 6 7 8 9 10; do
	grep -q '"--type", "heartbeat"' "$LOG" 2>/dev/null && break
	sleep 0.1
done
log_has '"--type", "heartbeat", "--subject", "alive", "--task-id", "task_0006", "--dispatch-id", "ctx_0001"'

: >"$LOG"
expect_exit 0 env -C "$WT" "$ORCW" w "done" --ok --summary "Done" --report "$TEST_ROOT/report.md" --files a.tf,b.tf
out_has "done   task_0006  succeeded  message msg_s1"
log_has '"send", "--type", "worker_done", "--subject", "Done", "--body", "Did the thing.\\n", "--task-id", "task_0006", "--dispatch-id", "ctx_0001", "--outcome", "succeeded", "--from", "term_agent1", "--dispatch-capability", "cap_secret_123", "--files-modified", "a.tf,b.tf"'
log_has '"--report-path", "'"$TEST_ROOT/report.md"'"'

# one-shot credentials on the verb itself, for a task with nothing stored
: >"$LOG"
expect_exit 0 env -C "$WT" "$ORCW" w "done" --ok "One shot" --body "$TEST_ROOT/report.md" --task task_0002 --from term_agent1 --dispatch-capability cap_inline
log_has '"--task-id", "task_0002", "--dispatch-id", "ctx_0001", "--outcome", "succeeded", "--from", "term_agent1", "--dispatch-capability", "cap_inline"'
grep -q cap_inline "$ORCW_HOME/workers/task_0002.json" || fail "inline credentials not stored"

FAKE_DISPATCH_STATUS=completed expect_exit 2 env -C "$WT" "$ORCW" w "done" --ok "Stale" --body "$TEST_ROOT/report.md"
log_lacks '"--subject", "Stale"'

: >"$LOG"
expect_exit 0 env -C "$WT" "$ORCW" w mail
out_has "mail   1 unread message(s)"
out_has "pin the tag"
log_has '"check", "--unread", "--terminal", "term_agent1"'
expect_exit 0 env -C "$WT" "$ORCW" w mail
out_has "mail   0 unread message(s)"

# ---------------------------------------------------------------- lost-response recovery is read-only
: >"$LOG"
expect_exit 0 "$ORCW" request 882fa58b-0000-0000-0000-000000000000
out_has "req    882fa58b-0000-0000-0000-000000000000  absent  no receipt here"
log_has '"request-show", "--request", "882fa58b-0000-0000-0000-000000000000"'

expect_exit 0 "$ORCW" w --help
out_has "Shared flags (every verb)"
out_has "--dispatch-capability <token>"

# ---------------------------------------------------------------- terminal reuse remains bound to its worktree
: >"$LOG"
expect_exit 0 "$ORCW" "done" dlv_0001 --reuse task_0001=task_0002
log_has '"worker-start", "--task", "task_0002", "--run", "run_test0001", "--worktree", "id:repo-1::'"$WT"'", "--terminal", "term_agent1"'

# ---------------------------------------------------------------- Orca error envelope printed whole
: >"$LOG"
expect_exit 1 "$ORCW" read ctx_0001
err_has '"code": "unknown_command"'
err_has "next: Using this same Orca CLI executable"
err_has "skills get orchestration --full"

echo "ok orcw"
