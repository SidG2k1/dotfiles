---
name: pr-update
description: Read a PR description via gh CLI and propose a concise update reflecting the current changes; never write without explicit user approval. Use when the user invokes /pr-update with a PR number or URL.
argument-hint: [pr-number-or-url]
---

Review the changes made this turn, then use the PR number or URL supplied by the user. If none was supplied and the current branch does not identify a PR, ask for one before continuing.

1. Run `gh pr view <pr-number-or-url> --json title,body,headRefName` to read the current PR description.
2. Preserve everything still relevant — existing test plan, manual context the user wrote. Don't strip content just because you didn't write it.
3. Decide what's worth adding. Stay focused on *why* and *how it was verified*. No filler, no emojis. Follow the active repository guidance. Run the drafted body through the `agentish-to-english` skill before showing it.
4. Show the proposed body in chat for the user to review before writing. If approved, update it with `gh pr edit <pr-number-or-url> --body "$NEW_BODY"`. If they push back, iterate in chat — don't rewrite the PR until they approve.
5. Match the voice of the existing description.
6. Don't use newlines for spacing inside a paragraph — GitHub wraps text.
