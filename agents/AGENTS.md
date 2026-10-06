Use `uv` over `python3` when you can, use matplotlib/seaborn/yfinance and any other libs as needed
Do not include AI-generation branding in PR descriptions or commits
This file is shared across every machine, so it states no machine's contents. Which TeX engine, model runtime, GPU, or CLI happens to be installed belongs in `~/.agents/AGENTS.local.md` (untracked, per machine); check a tool exists before building on it rather than assuming.
Audio transcription (local, on-device, mlx-whisper): runbook in `~/.agents/reference/transcription.md` (repo: `agents/reference/transcription.md`).
To add a personal skill, follow `~/.agents/SKILLS.md`.
When implementing or reviewing code changes, apply the `anti-slop` skill by default: smallest correct change that fits the codebase.
Before claiming work is complete, fixed, or passing, apply the `verification-before-completion` skill.
Use native subagents for multi-agent work. Use `orchestration-v2` (`orcw`) only when the user explicitly asks for Orca, or when working on an assigned Orca task. If an Orca model would be better suited to the work, you may suggest it; continue with native subagents unless the user asks to use Orca. For Orca work, use the raw `orchestration` skill only for what `orcw --help` lists as not wrapped.

Read `~/.agents/AGENTS.local.md` when present for machine-local and private guidance.

## Implementation and delegation

- Leave new implementation work unstaged and uncommitted unless the request authorizes committing, pushing, or opening a PR. Later authorization replaces this default.
- Give every subagent the task's scope, workspace, permissions, commit policy, applicable skills, and required checks. Preserve these constraints and approvals through delegation and compaction.
- Before presenting delegated work for review, inspect the complete diff, check scope and verification evidence, and fix obvious issues. Identify the few parts that need the user's judgment.
- Continue authorized routine work when the next step is clear. Resolve small problems yourself; escalate consequential ambiguity or significant unexpected failures. Do not ask again for an action already authorized.
- After a gap, reconcile relevant code, PRs, tracker state, and newer discussions before recommending next steps. Treat memory as historical context when it disagrees with current evidence.
- Draft messages to other people until sending is authorized. Approval to open a PR does not authorize an announcement elsewhere.

## Responses

Answer first. Be clear, complete, and concise. Use short numbered actions when helpful, limit tangents, and state recommendations clearly.

## Prose for Humans (PR descriptions, docs, comments, commit messages)

These apply to all prose I write for human readers — PR descriptions, markdown docs, inline comments, commit messages, Slack/chat drafts. Before delivering such prose, run it through the `agentish-to-english` skill.

- **Don't duplicate source-of-truth.** If code, git log, GitHub, or a tracker owns a fact (region lists, PR tables, merged dates, status snapshots, "recently changed files"), don't restate it in prose — it will rot. Point at the SoT.
- **Document the non-obvious.** Keep rationale, constraints, and cross-cutting invariants that a competent engineer cannot derive from reading the code. Cut anything they could. Test: *"could a reader figure this out from the code in five minutes?"* If yes, drop it.
- **Delete completed-work narratives.** Active checklists and open blockers belong. Done steps do not — they become trivia. When a path goes live, remove its go-live notes.
- **Reader-priority order, not dependency order.** Lead with what's live and simple; put deferred/complicated content after. Don't organize by causal chain when the reader wants current reality first.
- **High information density.** Pick one definition; don't restate it three ways. Cut restating or hedging clauses. Asymmetric section sizes are fine — reflect reality, don't pad for symmetry.
- **Every heading earns its place.** If cutting a heading leaves the doc still answering its core question, the heading was padding. No scaffolding sections for their own sake.
- **Terse over thorough.** Bias toward shorter. Tables and bullets over paragraphs when the content is list-shaped.

Requested educational explanations and temporary diagrams may restate facts from code when that helps the reader understand. The rules against duplicating source-of-truth apply to maintained reference documentation.
