---
name: orchestration-v2
description: >-
  Coordinate or hand off work to other agents in Orca with the `orcw` wrapper,
  and report back as an orcw worker. Coordinator: supervising workers, waiting
  for results, task DAGs, ask/reply, "hand off / another worktree / another
  agent" requests. Worker: your task spec carries an "orcw working agreement"
  and tells you to run `orcw w init`. Prefer this over the raw `orchestration`
  skill for the whole run lifecycle.
---

# Orca orchestration via orcw

`orcw --help` is the reference. This file is the decision and the loop.

## Decide first

- Before `orcw task` or `orcw handoff`, identify the worker agent. If the user
  did not name one, ask: "Which agent should I use (for example, codex, claude,
  or opencode)?" Wait for the answer, then pass it as `--agent <agent>`.
- "hand off", "handover", "give to another agent/worktree", a model or effort
  request: `orcw handoff --repo <r> --name <wt> --agent <agent> --spec <file>`,
  then stop.
- "supervise", "monitor", "wait for results", "coordinate", "DAG": the loop.
- Never substitute Claude/Codex subagents when the user asked for Orca.

## Coordinator loop

    orcw doctor                       # once per Orca version
    orcw run "<objective>"
    orcw task --agent <agent> --spec a.md   # worker in the current worktree
    orcw task --agent <agent> --spec b.md --after <task_a>   # deferred; wait launches it
    orcw wait --auto                  # releases, acks, launches deferred; stops on a question
    orcw reply <msg> "<answer>"       # for each question, then wait --auto again
    orcw status; orcw cleanup         # cleanup is a dry run without --apply

Manual form: `orcw wait`, then `orcw done <delivery> [--reuse <task>=<next>]`.

- One live worker per worktree. A second task in the same checkout is refused;
  use `--name <wt>` (new worktree), `--in <other>`, or `--share` knowingly.
- Specs are files; `orcw spec <file>` shows what the worker sees. They cannot be
  edited after creation: send corrections with `orcw tell <task> "<text>"`.
- A `wait` timeout is a checkpoint and prints status. Never release, stop, or
  restart a live worker. `REJECT` rows mean Orca refused a report; the task is
  still live.
- `done` refuses while a question is unanswered. Reply first.
- `--after` pastes the upstream report into the spec; nothing else carries
  data between tasks.
- Lost context? `orcw resume`. Lost a response? `orcw request <id>`.
  What happened to a task? `orcw log <task>`.
- Exit 1: Orca error printed whole. Exit 2: orcw refused, message says why.
  Exit 3: `orcw doctor` found a gap.

## Worker (your spec carries an orcw working agreement)

    orcw w init --from <handle> --capability <token>   # values from your preamble; once
    orcw w ids
    orcw w mail                       # before PR, tag, apply, or push
    orcw w ask "<question>" --options yes,no   # --timeout 10m default
    orcw w done --ok --summary "<status>" --report report.md --files a,b

Init infers the task and dispatch from the worktree and starts automatic
heartbeats. The preamble-file form remains available for shared worktrees.
After init, use `orcw w` instead of the preamble's raw commands. Exit 2 from a
`w` verb is orcw refusing (message says why); exit 1 is Orca's error, printed
whole. Send `done` once, then idle. No sub-workers.

## Not wrapped

Gates, remote `--on` workers, `worker-stop`, `worker-retain`, `reset`, legacy
Runs: `orca skills get orchestration`.
