---
name: memdump
description: Dump working context, learnings, open questions, and pointers to a memory file so a future session can resume the project. Use when the user invokes /memdump or asks to checkpoint before context is wiped.
argument-hint: [memory-file-path]
disable-model-invocation: true
---

Checkpoint the current project state into the memory file path supplied by the user. If no path was supplied, ask for one before writing.

1. **Read the file first** if it exists. Prefer editing over rewriting — preserve sections that are still accurate.
2. **If the user says they want to discard prior context**, clear the supplied memory file, read it back to confirm it's empty, then write the new dump.
3. **Reference any other guidance files** that explain the work (`AGENTS.md`, `CLAUDE.md`, agent plan files, design docs). Link to them by path rather than copying their contents.
4. **What to capture**: the goal of the project, current branch/PR state, what's done, what's in flight, open blockers, decisions and their rationale, and any non-obvious gotchas a future session would otherwise re-discover the hard way.
5. **Keep a `## Historical` section at the bottom** for stale context that's no longer load-bearing but might be useful for diagnosing future regressions or pitfalls.
