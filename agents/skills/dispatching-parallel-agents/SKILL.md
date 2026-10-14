---
name: dispatching-parallel-agents
description: Delegate independent investigations, reviews, or implementation tasks that can proceed without conflicting writes or unresolved dependencies.
---

# Dispatching Parallel Agents

Use native subagents for independent work. Keep tightly related changes together and investigate shared causes before splitting a task. Check for existing code or configuration that can satisfy the request before assigning new implementation.

## Dispatch

Give each worker only the context it needs:

- The requested outcome, acceptance criteria, and task scope.
- The workspace and files it owns; preserve unrelated work.
- Accepted decisions and assumptions, plus any conditions on deferred work.
- Permitted actions, commit policy, applicable skills, and required checks.
- Dependencies, useful source pointers, and the expected report.

Derive these from the user's request and applicable AGENTS.md guidance; pass the relevant guidance to workers that will not inherit it.

Use separate worktrees for concurrent implementation when writes could conflict. Read-only investigations can share a checkout. Keep dependent tasks sequential. Launch independent workers together and use focused follow-ups rather than redispatching completed work.

Establish shared interfaces and invariants before parallel implementation. Assign ownership of shared schemas, migrations, and cross-task contracts; keep dependent changes coordinated even when they touch separate files or repositories.

A worker should ask the coordinator about consequential choices or missing context.

## Review and integrate

Before asking the user to review:

1. Read the complete diffs and compare them with the agreed scope, assumptions, and permissions.
2. Inspect verification commands and results. Reuse valid evidence for unchanged code; run affected integration checks and repository-required checks as needed.
3. Fix obvious authorized issues, evaluate review findings against evidence, and inspect any resulting changes.
4. Present the few decisions or remaining risks that need the user's judgment.

After integration, inspect interactions between the changes, including failure behavior and cache invalidation. A clean merge or passing checks on individual branches do not establish that the assembled behavior is consistent.

Track task-created worktrees and temporary artifacts. Report their purpose and clean them up when no longer needed, preserving dirty files, unique commits, and other tasks' work.
