---
name: memload
description: Read a session memory file and re-verify state against the codebase before continuing. Use when the user invokes /memload to resume from a prior /memdump.
argument-hint: [memory-file-path]
disable-model-invocation: true
---

Resume from the memory file path supplied by the user. If no path was supplied, ask for one before continuing.

1. Read the memory file in full. Note the goal, the branch/PR state, what was done, what's still open, and any flagged gotchas.
2. Verify state before acting: check `git status`, the current branch, recent commits, and the files, symbols, and flags the memory mentions. If a source is unavailable, identify what remains unverified.
3. Briefly flag material changes, retire settled questions from the active task, and preserve the user's permissions and decisions. Loading memory alone does not authorize implementation or external writes.
