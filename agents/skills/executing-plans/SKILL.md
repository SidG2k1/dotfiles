---
name: executing-plans
description: Execute an agreed implementation plan, respecting its scope, permissions, dependencies, and review points.
---

# Executing Plans

Read the plan and current project state before starting. Preserve accepted decisions, assumptions, and conditions on deferred work; proposals are not implementation requirements.

Use the agreed execution method. Ordinary native delegation supports independent tasks under the existing unstaged-work default. Choose subagent-driven-development only when the user agreed to its committed workflow and commits are authorized.

## Execute

1. Verify the workspace, preserve unrelated changes, and inspect the plan for consequential gaps or conflicts.
2. Reconcile factual uncertainty from code and existing evidence. Ask about unresolved decisions that would materially change the work.
3. Execute authorized tasks in dependency order, using independent subagents where useful. Track enough progress to resume without repeating completed tasks.
4. Run the meaningful checks specified by the plan and repository. Reuse valid results for unchanged code; rerun affected checks after changes or failures.
5. Inspect the complete diff, check requirements and scope, fix obvious issues, and report the result with verification limits.

Do not expand the task to adjacent work when the requested action is blocked. Surface proposed scope additions separately.

Present integration options when a decision remains.
