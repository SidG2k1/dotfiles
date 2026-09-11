---
name: writing-plans
description: Use when the user asks for an implementation plan or when a large, complex task would benefit from proposing a structured workflow. Present plans in chat unless the user asks for a file or accepts a proposal that includes one.
---

# Writing Plans

## Overview

Write actionable implementation plans for an engineer who has little context about the codebase. Include the files, behavior, dependencies, and verification needed to implement each task. Follow the `anti-slop` skill: use the smallest correct change that fits the codebase.

Assume the reader is a skilled developer who is new to the project.

## Output and Workflow

- Present the plan in chat by default.
- Create or modify a plan file only when the user explicitly asks for one or accepts a proposal that clearly includes one. Do not treat task complexity alone as permission to write a document.
- For large, complex work, you may propose a fuller workflow: design discussion, optional reviewed spec, detailed plan, and staged execution. Explain the benefit and wait for acceptance before creating either document.
- For clear, bounded implementation requests, planning is optional. The model may state a concise approach in chat and implement directly.
- Match detail to the audience and execution method. A chat plan can be concise; a plan handed to another agent must be self-contained.

When the user requests a file, use their path or default to `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`.

**Context:** If working in an isolated worktree, it should have been created at execution time (Claude Code's worktree isolation, or `git worktree add`).

## Scope Check

If the work covers multiple independent subsystems, propose splitting it into independently useful, testable stages. A separate spec or plan file for each stage is optional and still requires user approval.

The remaining format is for detailed saved plans and plans handed to another agent. For a chat plan, include only the detail needed to make the sequence, decisions, and verification clear.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Task Right-Sizing

A task is the smallest unit that carries its own test cycle and is worth a
fresh reviewer's gate. When drawing task boundaries: fold setup,
configuration, scaffolding, and documentation steps into the task whose
deliverable needs them; split only where a reviewer could meaningfully
reject one task while approving its neighbor. Each task ends with an
independently testable deliverable.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Saved Plan Header

Use this header for a saved plan. Chat plans may use lighter formatting.

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

## Global Constraints

[The spec's project-wide requirements — version floors, dependency limits,
naming and copy rules, platform requirements — one line each, with exact
values copied verbatim from the spec. Every task's requirements implicitly
include this section.]

---
```

## Detailed Task Structure

Use this structure for saved plans and plans intended for handoff. Adapt or shorten it for chat when the same detail is unnecessary.

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Interfaces:**
- Consumes: [what this task uses from earlier tasks — exact signatures]
- Produces: [what later tasks rely on — exact function names, parameter
  and return types. A task's implementer sees only their own task; this
  block is how they learn the names and types neighboring tasks use.]

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## No Placeholders

Every step must contain the actual content an engineer needs. These are **plan failures** — never write them:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code — the engineer may be reading tasks out of order)
- Steps that describe what to do without showing how (code blocks required for code steps)
- References to types, functions, or methods not defined in any task

## Self-Review

After writing the complete plan, check it against the user's requirements and any available spec. This is a checklist you run yourself — not a subagent dispatch.

**1. Requirement coverage:** Can you point to a task that implements each requirement? List any gaps.

**2. Placeholder scan:** Search your plan for red flags — any of the patterns from the "No Placeholders" section above. Fix them.

**3. Type consistency:** Do the types, method signatures, and property names you used in later tasks match what you defined in earlier tasks? A function called `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a requirement with no task, add the task.

## Execution Handoff

- If the user asked only for a plan, present it and ask whether they want implementation.
- If they already asked for implementation, proceed after any required design decisions are settled.
- Use subagent-driven-development when the user chose that workflow and the saved plan has independent tasks.
- Use executing-plans when the user asks to execute a saved plan in a separate session.
