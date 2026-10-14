---
name: writing-plans
description: Use when the user asks for an implementation plan or when a large, complex task would benefit from proposing a structured workflow. Present plans in chat unless the user asks for a file or accepts a proposal that includes one.
---

# Writing Plans

Write actionable plans for a skilled developer who is new to the project. Specify behavior, interfaces, affected files, dependencies, and acceptance checks. Follow the `anti-slop` skill; a plan should describe the smallest correct change without doing the implementation in advance.

## Output and Workflow

- Present the plan in chat by default.
- Create or modify a plan file only when the user explicitly asks for one or accepts a proposal that clearly includes one. Do not treat task complexity alone as permission to write a document.
- For large, complex work, you may propose a fuller workflow: design discussion, optional reviewed spec, detailed plan, and staged execution. Explain the benefit and wait for acceptance before creating either document.
- For clear, bounded implementation requests, planning is optional. The model may state a concise approach in chat and implement directly.
- Match detail to the audience and execution method. A chat plan can be concise; a plan handed to another agent must be self-contained.

When the user requests a file, use their path or default to `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`.

## Scope and Decisions

Distinguish accepted requirements from proposals and conditional or deferred work. Preserve who made a consequential decision, its rationale, and any evidence or prerequisite that must be satisfied before implementation. Exploratory questions are not requirements. Carry these distinctions into task descriptions and tracker updates; do not turn a conditional decision into an unconditional task.

If the work spans independent subsystems, propose independently useful stages. Include only accepted work in the execution sequence. List consequential unresolved choices separately and settle them before the affected task starts.

## Task Structure

Identify the files each task changes and follow the codebase's existing organization. Do not plan file splits or refactors merely because a file is large; include them only when the requested behavior needs them.

Each task should produce a coherent change that can be reviewed and checked on its own. Fold setup, configuration, and documentation into the task that needs them. Split at meaningful dependency or review boundaries, not fixed time intervals.

Specify observable behavior, error cases, and interfaces the implementer needs. Include exact signatures or code snippets when they resolve a real ambiguity; full implementation and test bodies are optional. Link existing code and shared requirements instead of copying them into each task.

Name the acceptance checks and expected results. Reuse existing checks where they cover the behavior. Add a test only for a concrete regression it would catch; include a TDD cycle only when requested or warranted by the change. Verification should follow repository requirements and the scope of the change.

## Saved Plan Format

Adapt this format for a saved plan or an agent handoff. Keep chat plans lighter. Retain `Task N` headings for SDD's task-brief script; the coordinator supplies Global Constraints and accepted decisions separately.

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds]

**Approach:** [The intended behavior and relevant architectural choices]

## Global Constraints

[Binding project-wide requirements, exact values, and links to their sources.
Every task includes these constraints.]

## Decisions and Deferred Work

[Accepted decisions and rationale; unresolved proposals; deferred work with
its evidence condition or prerequisite.]

### Task N: [Coherent change]

**Behavior:** [What changes, including relevant error cases]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Existing checks: `tests/exact/path/to/test.py` [when relevant]

**Interfaces:**
- Consumes: [Required interfaces or links to existing definitions]
- Produces: [Interfaces later tasks depend on; exact signatures if needed]

**Dependencies:** [Prerequisites and decisions required before starting]

- [ ] Implement [the specified behavior using the existing pattern].
- [ ] Verify with [the relevant command or inspection] and confirm [expected result].
```

## Self-Review

Check the plan yourself against the current requirements and any accepted design:

- Every accepted requirement has a task; proposals and deferred work have not become scope.
- Each task has enough context to implement without guessing a consequential choice. Replace vague directions such as "handle edge cases" with the cases that matter; identify unresolved choices explicitly.
- Interfaces, names, dependencies, and exact values agree across tasks.
- Acceptance checks can detect a meaningful failure without duplicating the implementation.

Fix omissions and contradictions before handing off. If they require a new decision, present the choice rather than silently deciding it in the plan.

## Execution Handoff

- If the user asked only for a plan, present it and ask whether they want implementation.
- If they already asked for implementation, proceed after any required design decisions are settled.
- For ordinary delegated work, use native subagents with the task's scope, workspace, permissions, commit policy, and required checks. Delegation does not require SDD.
- Use subagent-driven-development only when the user has agreed to its committed workflow, commits are authorized, and the saved plan fits that workflow. Its commit-range review packages do not capture unstaged changes.
- Use executing-plans when the user asks to execute a saved plan inline or in a separate session.
