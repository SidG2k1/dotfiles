---
name: memdump
description: Save project context, decisions, assumptions, permissions, unresolved work, and source pointers for a future session. Use when the user invokes /memdump or asks to checkpoint before context is wiped.
argument-hint: [memory-file-path]
disable-model-invocation: true
---

Checkpoint the current project state into the memory file path supplied by the user. If no path was supplied, ask for one before writing.

1. Read the existing file first. Preserve useful, accurate context and remove
   obsolete material. Replace prior context entirely only when the user asks
   to discard it.
2. Capture the goal, scope, unfinished work, blockers, unresolved decisions,
   next useful step, and non-obvious constraints or gotchas.
3. Record accepted decisions, assumptions, conditions, and permissions with
   their rationale, who established or approved them, date, and source link or
   file reference when available.
   Distinguish user decisions from proposals and agent conclusions. Preserve
   conditions such as "only if the measurements show X" and the exact scope of
   authorization; do not turn an exploratory question into an approved feature.
   If the source cannot be recovered, say so rather than inventing provenance.
4. Link to authoritative guidance, designs, code, PRs, tickets, and discussions
   instead of copying their contents or maintaining another backlog. Include
   external status only when it helps resumption, labeled as a dated snapshot
   with its source and anything unverified.
5. Keep a `## Historical` section only when older context helps explain a
   current constraint or diagnose a future problem. Omit routine completed-work
   narratives. Read the saved file back to confirm it preserves the decisions,
   conditions, and unresolved work needed to resume.
