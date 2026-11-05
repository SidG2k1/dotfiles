# Laptop setup

Choose the components this laptop needs, then complete the relevant manual
steps below.

## 1. Prerequisites

```sh
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

git clone https://github.com/SidG2k1/dotfiles.git ~/dotfiles
```

Homebrew is needed only to install missing packages. With dependencies supplied
another way, use `--skip-brew`.

Homebrew's `shellenv` line goes in `~/.zprofile` or `~/.zshenv` **by hand** — the
repo does not install `~/.zprofile`, because other tools' installers append to it
and rewrite it on upgrade (`manifest.tsv` records why).

## 2. Install

```sh
cd ~/dotfiles
./install.sh list
./install.sh plan shell git vim     # example: choose your own components
./install.sh install shell git vim
bin/dotfiles-doctor
```

Future `./install.sh` runs apply this laptop's saved choices. Add components with
`install`; replace the choices with `select`. Removing a choice leaves its
existing files and packages in place. On a fresh laptop, a bare invocation
installs only the doctor helper. See `README.md` for where choices are saved.

Harness preferences (`claude`, `codex`, `opencode`), shared instructions
(`agent-shared`), personal skills (`skills`), and third-party skills plus
gh-stack (`agent-extras`) can be selected separately. Required components are
included automatically; `list` shows those relationships. Harness applications
and sign-in are separate manual steps.

### Package install safeguards

Enable the shared package-manager defaults on each laptop:

```sh
./install.sh install package-safety
bin/dotfiles-doctor --strict
```

The policy lives in [config/package-safety](config/package-safety). pnpm is
configured through its own CLI because its config format varies by version.
Update older package managers if they cannot read these settings; the installer
checks script-approval support before changing defaults, and the doctor checks
uv's cooldown support. Registry credentials stay local.

Release delays give time for compromises to be discovered; they do not certify
packages as safe. Project settings and command-line flags can override these
user defaults, and existing installs and lockfiles are not rescanned. Approve
reviewed dependency builds with `pnpm approve-builds` or `bun pm trust <package>`.
Bun also retains its built-in trusted-package list. Keep approvals in the project.
The project's own lifecycle scripts can run, so review an unfamiliar project's
scripts before installing dependencies.

npm rejects unapproved dependency scripts before installation. To inspect and
approve a dependency for the first time, stage it with scripts skipped:

```sh
npm install --ignore-scripts
npm install-scripts ls
npm install-scripts approve <package>
npm rebuild <package>
```

Keep macOS security updates enabled separately in System Settings. On current
macOS, check General → Software Update → Automatic Updates and Privacy & Security
→ [Background Security Improvements](https://support.apple.com/guide/mac-help/mchl44c4c70c/mac).
Docker image digests, editor extensions, and standalone downloads need their own
source and update choices; these defaults do not cover them.

## 3. Identity, auth, and other human-only steps

None of this is scriptable and none of it belongs in the repo. Sign in on each
new machine; never copy auth databases, keychains, token files, cookies,
sessions, or other app state from an old one.

```sh
# Git identity — tracked gitconfig has none, by design
git config --file ~/.gitconfig.local user.name  "<your name>"
git config --file ~/.gitconfig.local user.email "<your email>"

# Commit signing is not configured by this repo: the signer path and key are
# machine-specific, and on a managed Mac the provider is chosen for you. If you
# want it, set gpg.format / gpg.ssh.program / user.signingkey / commit.gpgsign
# in ~/.gitconfig.local, where they cannot break another machine.
```

- **CLI auth**: `gh auth login`, plus whichever cloud CLIs you use.
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

- **MCP servers and app integrations**: re-add by signing in.
- **GUI permission grants**: Ghostty (and any other terminal) needs
  Accessibility and Automation. BetterCmdTab needs Accessibility, plus Screen
  Recording for its Previews layout (Settings → Appearance → Layout). Leave its
  **Live window previews** off: it re-captures every window ten times a second,
  and leaked captures silence all notifications (see Troubleshooting). Mos does
  nothing until launched and granted Accessibility, then reverse scrolling is
  switched on in its own preferences, vertical and horizontal separately. Its settings live in a plist that `cfprefsd` owns and
  rewrites, so no tracked file can set them.

### Baseten router

The router and each client integration are independent choices. Install the
router without changing any harness settings:

```sh
./install.sh install router
~/.local/bin/baseten-router --setup
```

`--setup` installs the proxy runtime with known compromised releases excluded,
without starting it. Authentication and client sessions are separate from
installation.

If you use 1Password, install its CLI, sign in, and create
`~/.config/litellm/env` with your item's name or ID:

```sh
BASETEN_OP_ITEM="Baseten"
```

The item must hold the provider API key in its password field. Keep this file
local and run `chmod 600 ~/.config/litellm/env`. An exported `BASETEN_API_KEY`
takes precedence and works without 1Password. No credentials need to be copied
from the other laptop.

Start the proxy in one terminal:

```sh
~/.local/bin/baseten-router
```

Choose either client integration independently; the client applications must
already be installed. In another terminal, install and use the Claude profile:

```sh
./install.sh install router-claude
claude --settings "$HOME/.config/litellm/claude.json"
```

For OpenCode, register the provider and select it for a session:

```sh
./install.sh install router-opencode
opencode --model litellm/baseten-router
```

Neither integration changes the client's default model. Both profiles use port
4000. Model routing and pricing live in [the router config](config/litellm/baseten.yaml).

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

## 5. Editors

**vim** loads the plugins listed in `vim/plugins.txt` as native packages from
`~/.vim/pack/bundle/start/` (`:help packages`), with no plugin manager. Without
them vim still works, but every plugin-backed feature is silently inert, which is
harder to diagnose than an error. `./install.sh install vim-plugins` clones them;
`dotfiles-doctor` reports any that are missing and warns on a leftover pre-native-packages
`~/.vim/bundle`.

## 6. Optional Ghostty appearance

The optional Ghostty appearance preset is installed as
`~/.config/ghostty/appearance.ghostty` and is not loaded automatically. To use it
on another machine, copy its settings above the managed block in Ghostty's
`config`; local display adjustments stay outside that block.

## 7. Mermaid validation

`mermaid-check FILE.md` renders each Mermaid block in temporary storage and
leaves the Markdown unchanged. It requires `uv` and the pinned npm dependency
installed by this optional setup step:

```sh
./install.sh install mermaid
mermaid-check path/to/document.md
```

The dependency version is owned by `config/mermaid/package.json`. Rendering
checks syntax and tool compatibility, not whether a diagram accurately explains
its sources. The npm install may download a headless browser.

## 8. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ls` or `cat` fails in every shell | they are aliased to `eza`/`bat`; the alias needs the tool | `./install.sh install shell`. The aliases are defined only when the binary exists, so a stale `~/.zshrc` predating that guard is the other possibility — re-run `./install.sh` |
| A command using `eza` hangs forever, with no output | eza ≥0.23 reads **stdin** for paths when stdout is not a TTY and never returns if given no path argument. Agent, CI, and `$(…)` shells hit this | the guard lives in `~/.zshenv`, which every zsh reads — `.zshrc` is interactive-only and cannot fix it. Verify `~/.zshenv` is installed |
| `eza --icons .` → `invalid value '.' for '--icons [<WHEN>]'` | `--icons` takes an *optional* value in eza ≥0.23, so it swallows the next argument | spell the value — `--icons=auto`, which also correctly drops icons when piped — or terminate flags with `-- .`. The tracked `ls`/`la`/`ll`/`lt` aliases and the `~/.zshenv` guard use these respectively; a bare `--icons` anywhere is the bug |
| vim opens fine but `;th`, `:Tabularize`, ALE, and airline do nothing | the plugins are not in `~/.vim/pack/bundle/start/` — not cloned, or still in the old pathogen `~/.vim/bundle` location, which native-package vim never reads | see step 5 |
| Every `git diff` / `git show` / `git add -p` errors | `core.pager = delta` and `delta` is not installed | `brew install git-delta` |
| Every commit fails with a signing error | your `~/.gitconfig.local` sets `commit.gpgsign = true` but the signer or key is unavailable on this machine | fix the signer path and key in `~/.gitconfig.local`, or unset `commit.gpgsign` there |
| Claude Code status line shows the directory but no model, context, or rate limits | `~/.claude/statusline.sh` reads its JSON stdin with `jq`, so without `jq` only the git-derived parts render | `./install.sh install claude` |
| Glyphs render as tofu boxes | no Nerd Font | `./install.sh install fonts`; then select it in the terminal |
| Ghostty logs "unknown key" on start | that key is not in your Ghostty version | remove it from the `# >>> dotfiles` block; only append keys the installed version accepts |
| No notification banners or sounds from any app, with no Focus on | a window switcher or screen recorder left capture streams open, so macOS treats the display as shared and silences notifications; `/usr/bin/log show --last 10m --predicate 'eventMessage CONTAINS "Set auxiliary state"'` ends in `isScreenShared=1` | `killall replayd` clears the leaked streams; if it recurs, quit the app that leaks them |
