# Laptop setup

Run in order. Steps 1–2 are scripted; everything after exists because a script
cannot do it — it needs a password, a GUI toggle, or a decision.

## 1. Prerequisites

```sh
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

git clone https://github.com/SidG2k1/dotfiles.git ~/dotfiles
brew bundle --file=~/dotfiles/Brewfile.optional     # per-feature extras; read it first
```

The required `Brewfile` is not listed here: `./install.sh` in step 2 runs
`brew bundle` on it before it touches any config (`--skip-brew` opts out).
`Brewfile.optional` is the part no script decides for you; it also carries the
Ghostty and VS Code casks, since this repo installs configs for both.

Homebrew's `shellenv` line goes in `~/.zprofile` or `~/.zshenv` **by hand** — the
repo does not install `~/.zprofile`, because other tools' installers append to it
and rewrite it on upgrade (`manifest.tsv` records why).

Full Xcode, not just the Command Line Tools, is needed only for the AltTab build
in step 5. Skip it otherwise.

## 2. Install

```sh
cd ~/dotfiles
./install.sh --dry-run   # prints the plan: every target, its strategy, and what it will do
./install.sh
bin/dotfiles-doctor      # verifies each target landed and each dependency resolves
```

Idempotent, and safe to re-run after every `git pull`. Fix what `dotfiles-doctor`
reports before moving on — most of the troubleshooting section below is things it
catches for you.

## 3. Identity, auth, and other human-only steps

None of this is scriptable and none of it belongs in the repo.

```sh
# Git identity — tracked gitconfig has none, by design
git config --file ~/.gitconfig.local user.name  "<your name>"
git config --file ~/.gitconfig.local user.email "<your email>"

# Commit signing is not configured by this repo: the signer path and key are
# machine-specific, and on a managed Mac the provider is chosen for you. If you
# want it, set gpg.format / gpg.ssh.program / user.signingkey / commit.gpgsign
# in ~/.gitconfig.local, where they cannot break another machine.
```

- **CLI auth**: `gh auth login`, plus whichever cloud CLIs you use. Sign in; never
  copy an auth database, keychain, or token file between machines.
- **VS Code extensions** — install by identifier rather than copying the
  generated manifest:

```sh
for extension in \
  anthropic.claude-code enkia.tokyo-night formulahendry.code-runner \
  github.vscode-github-actions github.vscode-pull-request-github \
  ms-python.python ms-python.vscode-pylance ms-python.vscode-python-envs \
  ms-toolsai.jupyter ms-vsliveshare.vsliveshare
do code --install-extension "$extension"; done
```

- **Codex** `~/.codex/config.toml` is `never` in the manifest: Codex rewrites it
  with installation-specific marketplace paths, MCP servers, and project trust.
  Start from `agents/codex/config.toml` as a reference and copy keys across by
  hand.
- **MCP servers and app integrations**: re-add by signing in. Do not migrate
  cookie, session, or state files.
- **GUI permission grants**: Ghostty (and any other terminal) needs
  Accessibility and Automation; AltTab needs Accessibility plus Screen Recording
  (step 5). Mos does nothing until launched and granted Accessibility, then
  reverse scrolling is switched on in its own preferences, vertical and
  horizontal separately. Its settings live in a plist that `cfprefsd` owns and
  rewrites, so no tracked file can set them.

## 4. What must never enter this repo

It is a public repo. These stay out, permanently:

- API keys, OAuth tokens, `.env` files, cloud credential databases, CLI auth state
- SSH or GPG private keys
- Agent auth, memories, histories, sessions, project trust, generated MCP paths
- Email addresses, hostnames, employer-specific values, absolute `/Users/<name>` paths
- Vim swap, undo, view, and viminfo files

The machine-local seam files that hold this material instead — and the rule of
thumb for what belongs in them — are documented in `README.md`. Lock down any
local env file you restore:

```sh
chmod 600 ~/.env
```

## 5. Pinned AltTab source build

Optional, and the longest step. Pinned to v10.12.0 (`317a485b`), before AltTab's
Pro subsystem and source-tree restructure — deliberately giving up later upstream
work.

```sh
git clone https://github.com/lwouis/alt-tab-macos.git ~/src/alt-tab-macos
cd ~/src/alt-tab-macos && git switch -c pre-pro 317a485bcb090bf2b29e3f78872218f0099e1d62
```

Apply the three Sparkle patches by hand (they stay uncommitted local edits; the
script verifies them but does not write them):

- `Info.plist` — `SUEnableAutomaticChecks` → `false`
- `src/logic/Preferences.swift` — default `updatePolicy` → `.manual`
- `src/logic/events/PreferencesEvents.swift` — force both
  `automaticallyDownloadsUpdates` and `automaticallyChecksForUpdates` to `false`

Then `bin/rebuild-alttab` owns the rest:

| Command | Does |
| --- | --- |
| `rebuild-alttab check` | prerequisites + patch state, no build |
| `rebuild-alttab build` | build, ad-hoc sign, install to `/Applications`, launch |
| `rebuild-alttab reset-perms` | reset TCC state after a rebuild loses it |

Override the checkout location with `ALTTAB_SRC`.

Facts worth knowing before you debug something that is not broken:

- **Full Xcode is required** and must be the selected developer directory; the
  script refuses to build under the Command Line Tools and prints the three
  `xcode-select` / `xcodebuild` commands to fix it.
- **CocoaPods is not needed.** `Pods/` is committed at that commit. Build the
  *workspace*, not the project — the project alone will not resolve the pods.
- **Not notarized.** The build is ad-hoc signed, so `spctl -a` rejects it. This
  is harmless: a locally built bundle carries no quarantine attribute, so
  Gatekeeper does not gate its launch. Do not "fix" the spctl result.
- **The version string is literally `#VERSION#`.** A local Debug build leaves
  `CFBundleShortVersionString` unsubstituted; upstream CI fills it in at release
  time. Nothing is wrong.
- **The two TCC grants are GUI-only and cannot be scripted.** After a rebuild,
  grant AltTab under **Privacy & Security → Screen & System Audio Recording** and
  **→ Accessibility**. If approval still is not detected, remove and re-add
  `/Applications/AltTab.app` in both lists.
- **Sparkle has a fourth re-enable site, not three.**
  `src/logic/events/UserDefaultsEvents.swift:25` sets
  `automaticallyChecksForUpdates = true`. It is gated on
  `automaticallyDownloadsUpdates` already being true, which the patch above
  forces false, so it is unreachable in steady state — but it is precisely the
  stale-user-default path the three patches are meant to close. `rebuild-alttab
  check` reports it as expected rather than pretending three sites is the whole
  story.

## 6. Editors

**vim** wants nine plugins, loaded as native packages from
`~/.vim/pack/bundle/start/` (`:help packages`) — no plugin manager. A machine
without them still gets a working vim, but every plugin-backed feature is
silently inert, which is a worse failure to diagnose than an error would be.
Plugins are third-party checkouts and deliberately not vendored; `vim/plugins.txt`
lists the nine, each annotated with the vimrc setting or mapping it backs, and
carries the clone commands in its header. `install.sh` clones them;
`dotfiles-doctor` reports any that are missing, and warns on a leftover
pre-native-packages `~/.vim/bundle`.

## 7. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ls` or `cat` fails in every shell | they are aliased to `eza`/`bat`; the alias needs the tool | `brew bundle --file=Brewfile`. The aliases are defined only when the binary exists, so a stale `~/.zshrc` predating that guard is the other possibility — re-run `./install.sh` |
| A command using `eza` hangs forever, with no output | eza ≥0.23 reads **stdin** for paths when stdout is not a TTY and never returns if given no path argument. Agent, CI, and `$(…)` shells hit this | the guard lives in `~/.zshenv`, which every zsh reads — `.zshrc` is interactive-only and cannot fix it. Verify `~/.zshenv` is installed |
| `eza --icons .` → `invalid value '.' for '--icons [<WHEN>]'` | `--icons` takes an *optional* value in eza ≥0.23, so it swallows the next argument | spell the value — `--icons=auto`, which also correctly drops icons when piped — or terminate flags with `-- .`. The tracked `ls`/`la`/`ll`/`lt` aliases and the `~/.zshenv` guard use these respectively; a bare `--icons` anywhere is the bug |
| vim opens fine but `gc`, `;th`, `:Tabularize`, ALE, and airline do nothing | the plugins are not in `~/.vim/pack/bundle/start/` — not cloned, or still in the old pathogen `~/.vim/bundle` location, which native-package vim never reads | see step 6; `dotfiles-doctor` names the missing ones and flags a leftover `~/.vim/bundle` |
| Every `git diff` / `git show` / `git add -p` errors | `core.pager = delta` and `delta` is not installed | `brew install git-delta` |
| Every commit fails with a signing error | your `~/.gitconfig.local` sets `commit.gpgsign = true` but the signer or key is unavailable on this machine | this repo configures no signing, so it is local: fix the signer path and key in `~/.gitconfig.local`, or unset `commit.gpgsign` there |
| Claude Code status line shows the directory but no model name | the `statusLine` command reads the model out of its JSON stdin with `jq`, and guards on it, so a missing `jq` costs the model half and nothing else | `brew install jq` (it is in `Brewfile`) |
| Glyphs render as tofu boxes | no Nerd Font | `brew bundle --file=Brewfile` installs it; then select it in the terminal |
| Ghostty logs "unknown key" on start | that key is not in your Ghostty version | remove it from the `# >>> dotfiles` block; only append keys the installed version accepts |
