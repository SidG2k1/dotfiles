# Code Reviewer Prompt Template

Use for the final whole-branch review after SDD task reviews.

**Model:** [MODEL] — required; apply the model policy in SKILL.md and set the native dispatch parameter.

**Task:** Review the completed SDD branch

**Prompt:**

```text
Applicable guidance: [APPLICABLE_GUIDANCE — relevant AGENTS.md instructions and task-specific working agreement]

Independently review the completed branch against its accepted requirements
and surrounding code.

What changed: [DESCRIPTION]
Plan or requirements: [PLAN_OR_REQUIREMENTS]
Binding constraints and assumptions: [GLOBAL_CONSTRAINTS]
Rejected and deferred findings with their dispositions and evidence:
[FINDING_DISPOSITIONS]
Base: [BASE_SHA]
Head: [HEAD_SHA]
Review package: [DIFF_FILE]
Verification reports: [REPORT_FILES]

Read the review package, requirements, and relevant surrounding code.
If the package is unavailable or does not match the requested revisions,
inspect the exact BASE..HEAD diff yourself and state the limitation.
Inspect the complete change, not just summaries or selected files.

Keep this checkout, index, HEAD, and branch state unchanged. If another
revision requires a working copy, use an owned temporary checkout only
within the permitted scope; identify it and its cleanup owner.

Focus on requirements, integration across tasks, compatibility, and concrete
correctness or security risks. Trace relevant callers, data flow, failure
behavior, and tests. Compare findings with accepted assumptions and
decisions before declaring a defect. Flag a problem in the plan separately
from an implementation failure.

Independently evaluate every rejected or deferred finding against its original
claim, recorded reason, supporting evidence, and the final diff. Do not accept
the coordinator's ruling as proof. Report any unsupported ruling or deferred
required fix with concrete evidence. Do not repeat a rejected finding without
new evidence, a relevant diff or requirement change, or evidence that the
recorded ruling was unsound. State which dispositions you checked and whether
they remain justified.

Apply anti-slop: distinguish required corrections from optional improvements
and hypothetical concerns. Do not turn a review into new features,
unrelated refactoring, or documentation that restates code.

Inspect verification commands and results for the current code. Passing
tests do not establish requirement coverage, and a report's summary does
not prove a run passed. Reuse valid evidence; run a permitted focused check
only for a concrete unresolved doubt. State any unverified behavior.

Report findings first, ranked by their effect on the requested outcome.
For each finding, give file:line evidence, the concrete failure or impact,
and the needed correction when clear. Keep optional observations separate.

Finish with:
- Readiness for the requested integration: ready | needs fixes | needs a decision.
- Any unresolved requirements, assumptions, or verification limits.
- A short explanation supporting the assessment.

If no findings remain, say so with the scope and limits of the review.
```
