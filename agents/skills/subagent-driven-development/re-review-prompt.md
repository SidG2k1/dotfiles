# Scoped Re-Review Prompt Template

Use this template when dispatching a re-review after a fix round. The
re-reviewer verifies the findings were addressed and checks the fix diff for
new breakage. It is not a fresh review — the full review already happened.

**Purpose:** Verify each finding from the previous review was addressed, and
that the fix itself broke nothing.

**Model:** [MODEL] — required; apply the model policy in SKILL.md and set the native dispatch parameter.

**Task:** Re-review Task N, fix round R

**Prompt:**

```text
Applicable guidance: [APPLICABLE_GUIDANCE — relevant AGENTS.md instructions and task-specific working agreement]

You are re-reviewing one task's fix round. A previous review produced
findings; an implementer has attempted to fix them. Your job is to
verdict each finding and inspect the fix diff — nothing else.

## The Task

Read the task brief: [BRIEF_FILE]

Binding requirements, accepted assumptions, and scope:
[GLOBAL_CONSTRAINTS]

## The Findings Under Verification

[FINDINGS]

## The Fix

Read the implementer's report (fix reports are appended at the end):
[REPORT_FILE]

**Fix base:** [FIX_BASE_SHA] (the head the previous review saw)
**Head:** [HEAD_SHA]
**Diff file:** [DIFF_FILE]

Read the diff file once — it contains the fix commits, a stat summary,
and the fix diff with surrounding context. Do not re-run git commands.
If the diff file is missing, fetch the diff yourself:
`git diff --stat [FIX_BASE_SHA]..[HEAD_SHA]` and
`git diff [FIX_BASE_SHA]..[HEAD_SHA]`.

Your review is read-only on this checkout. Do not mutate the working
tree, the index, HEAD, or branch state in any way.

## Scope

Your scope is the findings list and the fix diff. Verdict every finding.
Inspect the fix diff for new problems the fix itself introduced. Do NOT
re-review code the fix did not touch: if you notice an issue entirely
outside the fix diff, report it under Out-of-Scope Observations — it
does not block this task and does not extend the loop. A broad
whole-branch review happens after all tasks are complete.

## Verification

Inspect the fix report's applicable commands, output, exit status, and
scope, and compare its claims with the diff and binding requirements.
Reuse valid evidence for unchanged code. Run a permitted focused check
only for a concrete gap in the existing evidence; report broader or
unavailable validation when it is needed but outside this review's
permissions. Do not assume every fix needs a new test or TDD proof.

## Output Format

Your final message is the report itself: begin directly with the first
finding's verdict. Every line is a verdict, a finding with file:line,
or a check you ran — no preamble, no process narration.

### Finding Verdicts

For each finding in The Findings Under Verification, in order:
- **[finding one-liner]** — ADDRESSED | NOT ADDRESSED, with file:line
  evidence. "Attempted" is not addressed: the specific defect must no
  longer exist.

### New Breakage in the Fix Diff

Anything the fix itself broke or introduced, with severity
(Critical/Important/Minor) and file:line. "None" if clean.

### Out-of-Scope Observations

Issues you noticed entirely outside the fix diff. Non-blocking; the
controller ledgers these for the final review. "None" if none.

### Verdict

**Fix round:** [All findings addressed, no new Critical/Important
breakage | Findings remain open] — list the open ones.
```

**Placeholders:**
- `[MODEL]` — required model selected using SKILL.md's model policy
- `[BRIEF_FILE]` — the task brief file (same file the implementer worked from)
- `[GLOBAL_CONSTRAINTS]` — binding requirements, accepted assumptions, and scope supplied separately from the task brief
- `[FINDINGS]` — the Critical/Important findings and spec gaps from the
  previous review, copied verbatim, one per bullet
- `[REPORT_FILE]` — the implementer's report file (fix reports appended)
- `[FIX_BASE_SHA]` — the head the previous review saw
- `[HEAD_SHA]` — current commit
- `[DIFF_FILE]` — the path `scripts/review-package PLAN_FILE FIX_BASE HEAD` printed

**Re-reviewer returns:** per-finding verdicts (ADDRESSED / NOT ADDRESSED),
new breakage in the fix diff, out-of-scope observations, and a round verdict.
