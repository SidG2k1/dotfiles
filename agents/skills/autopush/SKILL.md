---
name: autopush
description: Stage selectively, commit, and push the current branch, then refresh the PR description if one exists. Use when the user invokes /autopush after a change is ready to ship.
disable-model-invocation: true
---

Run in order. Stop and surface output if any step fails — don't retry blindly.

1. `git status` — confirm what's modified and untracked.
2. `git diff --staged` (and `git diff` if useful) — confirm the change is what you expect.
3. `git add <paths>` — stage only files relevant to this change. **Never** `git add .` or `git add -A`; scratch/tmp files in the worktree stay out of the commit.
4. `git commit -m "<message>"` — write a thoughtful commit message explaining the *why*, phrased per the `agentish-to-english` skill. The subject is the PR title if this is a new branch; lead with a clear, scannable line.
5. `git push` — the `push.autoSetupRemote` config handles new branches automatically.
6. Check if a PR exists: `gh pr view --json url,number 2>/dev/null`. If yes, invoke the `pr-update` skill with that PR number to refresh the description. If no, mention the `gh pr create` command to the user — don't open the PR autonomously.
