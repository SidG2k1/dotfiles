---
name: subagent-driven-development
description: Execute an agreed implementation plan with committed tasks and independent reviews when commits are authorized.
---

# Subagent-Driven Development

Use this workflow when the user agreed to committed implementation tasks and independent task reviews. Its ledger and review packages depend on commit ranges. For ordinary unstaged work, use executing-plans or dispatching-parallel-agents with the existing permissions.

## Setup and recovery

Verify an isolated worktree and preserve unrelated work. Do not start implementation on main/master without explicit consent.

Read the plan and current project state. Preserve accepted requirements, assumptions, permissions, and conditions on deferred work. Resolve factual uncertainty from existing evidence. Batch consequential plan conflicts for the user before dependent implementation.

Each plan owns a git-ignored workspace. Run this skill's `scripts/sdd-workspace PLAN_FILE` to obtain its directory. Keep its ledger at `<workspace>/progress.md`, with briefs, reports, and review packages alongside it; leave other plans' artifacts alone.

- Identify the ledger with `# SDD ledger — plan: <plan file path>`.
- Record the branch's starting commit for the final review.
- Record completed tasks as `Task <N>: complete (commits <base7>..<head7>, review clean)`.
- Record finding dispositions and any unresolved fix round with their evidence and commit ranges.

After interruption or compaction, reconcile the ledger with git and current files. Resume unfinished work rather than redispatching completed tasks. A ledger for another plan is not this plan's progress.

## Dispatch an implementation task

Work on one implementation task at a time in the SDD worktree so its commit range and dependencies remain clear. Independent unstaged tasks belong in the ordinary parallel-delegation workflow.

Record BASE with `git rev-parse HEAD` before dispatch. Do not infer it later from `HEAD~1`, which can omit part of a multi-commit task.

1. Run `scripts/task-brief PLAN_FILE N` to extract the task text. The script does not include the plan's Global Constraints.
2. Give the worker the brief path, binding Global Constraints, workspace, relevant interfaces and accepted decisions, permitted actions, authorized commit policy, applicable skills, and required checks.
3. Name its report file alongside the brief. Keep large artifacts in files and return a short report rather than copying the session's history.
4. Record the worker's identity and selected model so follow-up fixes can reuse its context and model choice.

### Model selection

Name a model for every dispatch, including reviewers and follow-up fixes, and pass it through the native tool's model selector. Check available model identifiers; do not silently inherit the session model. If the tool cannot select models, identify the inherited model explicitly and report that limitation.

Use at least a mid-tier model for implementation from prose requirements and for reviews. Use cheaper models only for mechanical, fully specified work. Difficult integration, concurrency, or open design questions may justify a stronger model.

Optimize total task cost and time, including retries and review fixes. In these sessions, cheaper models often needed enough extra turns to erase their savings; do not treat their per-turn price as the task's cost.

Template: [implementer-prompt.md](implementer-prompt.md).

## Handle the worker's report

- **DONE:** Inspect the reported changes and verification evidence, then prepare the task review.
- **DONE_WITH_CONCERNS:** Resolve correctness or scope concerns before treating the task as complete. Record optional observations for later review.
- **NEEDS_CONTEXT:** Supply the missing context from available sources.
- **BLOCKED:** Investigate the cause, clarify the task, or change the approach. Ask the user when a consequential decision, missing authority, or unresolved failure requires them.

Do not repeat the same unsuccessful dispatch without changing the information or approach.

## Review the task

Run `scripts/review-package PLAN_FILE BASE HEAD` and pass its returned path to an independent reviewer. The script includes the commit list, stat, and complete diff. Commit authorized task fixes before generating their review package so the package contains them.

Give the reviewer the task brief, report, diff, and binding requirements and assumptions. Include any previous findings in the area. Let the reviewer form its own conclusions; do not dictate a verdict.

Require a verdict on both specification compliance and code quality. Self-review alone does not replace this review. Inspect the actual verification commands and results; do not ask the reviewer to repeat valid tests against unchanged code.

If the reviewer cannot verify a requirement from the diff because it concerns unchanged code or another task, investigate it before marking the task complete.

Template: [task-reviewer-prompt.md](task-reviewer-prompt.md).

## Evaluate findings and fix genuine issues

Compare each finding with the code, accepted requirements, assumptions, and evidence before dispatching a fix.

- Reject incorrect or out-of-scope findings only with code, requirement, or other concrete evidence supporting the ruling.
- Defer optional improvements with a recorded reason.
- Resolve consequential conflicts with the accepted plan through the user.
- Fix genuine correctness or requirement failures and obtain a focused re-review.

These decisions can happen in any round. Five fix rounds per task is a maximum, not a prerequisite for judgment. Do not defer a required fix and call the task complete.

For each rejected or deferred finding, preserve its original wording, disposition, reason, supporting evidence, and reviewed commit range in the ledger. Pass all these records to the final independent reviewer; a coordinator's ruling does not settle whether the finding is valid. Reopen a rejected finding when new evidence or a relevant change to the diff or requirements undermines that ruling.

Prefer resuming the original worker for a fix. When repeated attempts fail to make progress, use fresh context or a more suitable model and carry forward what was tried. An obvious authorized correction may be made by the coordinator; it still needs diff inspection, relevant verification, an authorized commit, and review before completion.

For each fix:

1. Record FIX_BASE before editing.
2. Run checks covering the amended behavior and inspect the result. Reuse other evidence that remains valid; preserve repository-required checks.
3. Append the fix and its evidence to the task report.
4. Generate `scripts/review-package PLAN_FILE FIX_BASE HEAD` and request a re-review. Supply the findings, brief, report, binding requirements and assumptions, and fix diff.

The re-review checks whether the findings were addressed and whether the fix introduces breakage. Optional observations on unrelated code do not extend the task.

Record each round as `Task <N>: fix round <R>/5 (<addressed>, <open>; commits <base7>..<head7>)`, with finding details and rulings. Stop repeating fixes at the cap. Report unresolved required behavior or correctness failures to the user rather than claiming completion.

Template: [re-review-prompt.md](re-review-prompt.md).

## Complete the task and branch

Before recording a task as complete, inspect its full diff, verification evidence, and review verdicts. Required findings must be fixed or resolved by a user decision; record any agreed deferrals. Then update the ledger and proceed to the next task.

After the tasks finish, generate a whole-branch review package using the recorded branch starting commit and current HEAD. Give the final reviewer the plan, diff, and all rejected and deferred findings with their dispositions and evidence. It must independently assess those rulings as well as integration and cross-task behavior.

Template: [code-reviewer.md](code-reviewer.md).

Evaluate final findings before fixing them. Group related genuine fixes in one dispatch, verify the changed behavior, and obtain a focused re-review. Avoid one worker per finding or repeated broad review waves. Surface unresolved requirements, consequential choices, or recurring failures to the user.

Inspect the final complete diff and confirm applicable checks still cover it. Run any remaining repository-required checks; do not repeat a full suite solely because this phase ended.

Present the result and remaining integration choices.

Remove this plan's temporary workspace when its reports are no longer needed and cleanup is authorized. Preserve other plans' artifacts, dirty worktrees, and unique commits.
