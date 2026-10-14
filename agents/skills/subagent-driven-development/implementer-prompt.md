# Implementer Subagent Prompt Template

Use for an SDD task whose committed workflow is agreed and authorized.

**Model:** [MODEL] — required; apply the model policy in SKILL.md and set the native dispatch parameter.

**Task:** Implement Task N: [task name]

**Prompt:**

```text
Applicable guidance: [APPLICABLE_GUIDANCE — relevant AGENTS.md instructions and task-specific working agreement]

You are implementing Task N: [task name].

Read [BRIEF_FILE] first. It contains the task text.
Binding Global Constraints: [GLOBAL_CONSTRAINTS]

Context: [where this task fits, dependencies, interfaces, accepted decisions]
Workspace and owned files: [DIRECTORY_AND_FILES]
Scope, assumptions, and permitted side effects: [TASK_SCOPE_AND_PERMISSIONS]
Authorized commit policy: [TASK_COMMIT_POLICY]
Applicable skills and required checks: [SKILLS_AND_CHECKS]
Report path: [REPORT_FILE]

Preserve unrelated work and stay within the supplied task scope.

Implement the agreed behavior using anti-slop: reuse existing patterns,
keep the change focused, and add tests only for a concrete regression or
required behavior. Follow TDD when the task requires it.

Ask the coordinator about consequential choices, missing authority, or
failures you cannot resolve.

Run focused checks while editing and all repository-required checks before
completion. Reuse inspected results for unchanged code; rerun affected
checks after relevant changes or failures. Report unavailable checks
honestly.

Review the full diff for requirement coverage, scope, integration, and
removable complexity. Fix obvious issues. Create only the authorized task
commit(s), preserving unrelated files and running required commit hooks.

Write the full report to [REPORT_FILE]:
- Behavior implemented and relevant files.
- Verification commands, results, and any limitations.
- Evidence that a regression test detects the original bug when claimed.
- Self-review findings, unresolved questions, and concerns.

Then return a short report:
- Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- Commits created (short SHA and subject).
- Verification summary and limits.
- Concerns and report-file path.

If BLOCKED or NEEDS_CONTEXT, include the missing decision or information in
the reply so the coordinator can act on it.

For a follow-up fix, inspect the supplied finding against the task and
code. Fix genuine issues, rerun affected checks, create the authorized fix
commit, and append the result to the same report. Raise a conflicting or
unsupported finding with evidence rather than changing accepted behavior
to satisfy it.
```
