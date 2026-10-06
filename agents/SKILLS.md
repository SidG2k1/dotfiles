# Personal skills — layout, linking, and porting between tools

One copy of this file, symlinked into `~/.claude/skills/README.md` and `~/.codex/skills/README.md`,
the same way `~/.agents/AGENTS.md` feeds both tools' instruction files.

Nothing in either skills directory should be a real file. Every entry is a symlink into `~/.agents/`,
so a skill is edited in one place and adopted by a tool by adding one link.

## Two layers

The only difference is whether the real content sits in the public dotfiles repo.

**Portable** — `github.com/SidG2k1/dotfiles` is public, so this layer must name no internal host.

```
~/dotfiles/agents/skills/<name>/SKILL.md                                     # committed
~/.agents/skills/<name>  -> ~/dotfiles/agents/skills/<name>                     (absolute)
~/.claude/skills/<name>  -> ../../.agents/skills/<name>                         (relative)
~/.codex/skills/<name>   -> ../../.agents/skills/<name>                         (relative)
```

**Local-only** — for anything naming internal infrastructure, a private host, or a fact that could be
false on another machine.

```
~/dotfiles/private/agents/skills/<name>/SKILL.md              # ignored by the public repo
~/.agents/skills.local -> ~/dotfiles/private/agents/skills
~/.claude/skills/<name>  -> ../../.agents/skills.local/<name>
~/.codex/skills/<name>   -> ../../.agents/skills.local/<name>
```

`skills.local/` is a seam in the dotfiles machine-local layer alongside `~/.zshrc.local` and
`~/.agents/AGENTS.local.md` — see **Machine-local layer** in `~/dotfiles/README.md`. The naming
carries the signal — a real directory under `skills.local/` is deliberate; a real directory under
`~/.agents/skills/` or in a tool's skills dir is a mistake, except the vendored skills the skills CLI
installs there (listed in `~/dotfiles/manifest.tsv` under *"NOT rows in this manifest, on purpose"*).

## Adding one

1. Create `<name>/SKILL.md` under `~/dotfiles/agents/skills/` (portable) or
   `~/dotfiles/private/agents/skills/` (local-only).
2. Portable only: in `~/dotfiles/.gitignore`, add a `!/agents/skills/<name>/...` line for each tracked
   file (`SKILL.md`, and `agents/openai.yaml` if the skill has one); in `~/dotfiles/manifest.tsv`, add
   a row for the `~/.agents/skills/<name>` link. Without the `.gitignore` line, `git add` refuses and
   `git status` stays silent. Skip either and the skill works on this machine but is missing on the
   next. A local-only skill needs neither: the private manifest links the whole
   `private/agents/skills/` directory to `~/.agents/skills.local`.
3. Run `./install.sh --only agents` (portable) or `./install.sh --only private` (local-only) from
   `~/dotfiles` to link the skill into `~/.claude/skills/` and `~/.codex/skills/`.

Verify the paths land on one file rather than merely existing — a dangling link fails silently and the
skill just never appears:

```bash
stat -L -f %i ~/.agents/skills{,.local}/<name>/SKILL.md \
              ~/.{claude,codex}/skills/<name>/SKILL.md 2>/dev/null
```

`-L` matters: without it macOS `stat` reports the symlink's own inode, so identical files look
different and you chase a problem that isn't there.

## Porting a skill between Claude Code and Codex

The shared shape is real: both discover `<name>/SKILL.md` under their skills directory, both parse YAML
frontmatter with `name` and `description`, and both use sibling `scripts/`, `references/`, `assets/`,
`agents/` directories for bundled resources. Most skills move by symlink alone, which is why the local
layer points both tools at one file.

What is not shared is frontmatter keys. Unknown keys are ignored rather than fatal, so a skill carrying
another tool's keys still loads — it just silently loses that behavior.

| Key | Honored by | Effect |
| --- | --- | --- |
| `name`, `description` | both | discovery and match |
| `metadata.short-description` | Codex | short label; Claude Code ignores it |
| `disable-model-invocation` | Claude Code | hides it from the model, leaving `/<name>` for you to type |
| `argument-hint` | Claude Code | argument hint on the slash command |
| `allowed-tools` | Claude Code | tool grant for the skill |

Two cautions when bringing in a skill written for another tool:

- **Shell-exec markers are live in Claude Code.** A `` !`cmd` `` or a ```` ```! ```` fence executes on
  load. In tools that treat those as plain text they are inert, so a skill can carry one harmlessly and
  then run it here. Read the body before linking a skill you did not write.
- **Oversized `SKILL.md` is skipped, not truncated.** Claude Code drops a skill whose file exceeds its
  size ceiling, so a large ported skill can go quiet with no error. Split detail into `references/`.

`~/.codex/skills/.system/` is Codex's own managed set (`skill-creator`, `review-agent`, `openai-docs`, …).
Leave it alone; personal skills go beside it, not inside it.

## Three things that look broken but aren't

**A skill missing from the model's list.** `disable-model-invocation: true` hides it from the listing
the model sees while leaving `/<name>` working. Check frontmatter before debugging the link.

**Forks of the superpowers plugin.** The skills noted as *"Forked from superpowers 6.2.0"* in
`~/dotfiles/manifest.tsv` were copied from github.com/obra/superpowers so the plugin's per-session
SessionStart hook could be removed. Nothing updates them from upstream; they are maintained by hand.

**Private layer backup.** Gitignoring `private/` keeps it out of the public repository but does
not back it up. Adding a remote for private content needs a separate decision about which host is
approved; the public repo must never track that content.
