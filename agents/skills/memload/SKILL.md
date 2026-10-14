---
name: memload
description: Read session memory and reconcile decisions, permissions, and unresolved work with current code and available project sources. Use when the user invokes /memload to resume from a prior /memdump.
argument-hint: [memory-file-path]
disable-model-invocation: true
---

Resume from the memory file path supplied by the user. If no path was supplied, ask for one before continuing.

1. Read the memory file in full. Identify the goal, unresolved work, accepted
   decisions, assumptions, conditions, and recorded permissions. Check their
   provenance; proposals and agent conclusions do not establish user approval.
2. Reconcile relevant current code before continuing: inspect the working tree,
   branch, recent commits, and the files or behavior the next step depends on.
   After a gap, also check relevant PRs, tracker state, and newer discussions
   through available sources. Treat dated status snapshots as historical;
   current authoritative sources govern facts.
3. If a source is unavailable, mark the affected claims unverified. Do not
   rely on an unverified prerequisite or permission for a consequential action.
4. Briefly report material changes and the next useful step. Retire settled
   questions, preserve accepted decisions and their conditions, and raise
   conflicts that require the user rather than silently choosing new scope.
   Keep the backlog in its existing source of truth.

Loading memory alone does not authorize implementation or external writes.
Honor established authorization only within its recorded scope and subject to
the current request and applicable instructions.
