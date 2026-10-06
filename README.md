# dotfiles

Public, credential-free configuration for a macOS (Apple Silicon) development
laptop: zsh with vi mode, vim with native packages, Ghostty, starship, and the Claude
Code / Codex agent setup. No identity, keys, tokens, internal hostnames, or absolute
`/Users/...` paths are tracked here — those live in machine-local files this repo
deliberately does not own (see [Machine-local layer](#machine-local-layer)).
Everything degrades gracefully: a missing tool costs a feature, never `ls`,
`cat`, `cd`, `git`, or shell startup.

## Quick start

```sh
git clone https://github.com/SidG2k1/dotfiles.git ~/dotfiles
cd ~/dotfiles
./install.sh                         # idempotent; --dry-run prints the plan
bin/dotfiles-doctor                  # verifies every install landed + deps resolve
```

`install.sh` runs `brew bundle --file=Brewfile` itself (`--skip-brew` opts out);
the per-feature extras in `Brewfile.optional` are the one dependency step it
leaves to you. It never overwrites a file it does not own — see the strategies
below for why that distinction exists.

Then do the parts a script cannot: `setup.md`.

## Install strategies

"Install a dotfile" is not one operation. Some targets the repo can own
outright; others are actively rewritten by the tool that reads them, or carry
machine identity that a symlink would destroy. Picking the wrong strategy is how
dotfiles repos silently eat a working machine's config.

| Strategy | Use when |
| --- | --- |
| `link` | no tool writes to the file (`vimrc`, `starship.toml`) |
| `wrap` | the config needs a per-machine tail (`~/.zshrc`) |
| `include` | the target holds identity or tool-written blocks (`~/.gitconfig`, and its `[filter "lfs"]`) |
| `append-once` | the tool and the human both edit the same file (`~/.config/ghostty/config`) |
| `merge-json` | the app writes the file from its own UI (`~/.claude/settings.json`, VS Code, Docker) |
| `merge-toml` | an app owns the TOML file |
| `never` | another tool's installer owns the target and regenerates it on upgrade (`~/.zprofile`, `~/.profile`) |

**`manifest.tsv` is the single source of truth.** Its header defines what each
strategy does; its rows say which file goes where, under which strategy, what
breaks if the strategy is wrong, and what is deliberately *not* installed.

## Machine-local layer

Private configuration can live under gitignored `private/`. If
`private/manifest.tsv` exists, the installer applies it after the public manifest;
its source paths are relative to `private/`. `./install.sh --only private`
installs that layer alone. Targets may overlap the public manifest for
complementary `merge-json` or `merge-toml` subsets; other targets must be distinct.
The doctor checks both manifests and optional executable names in
`private/executables.txt`.

Rule of thumb: **if a statement could be false on another machine, it goes in a
`.local` file.** Machine truth is not portable config, and asserting it in a
tracked file is worse than omitting it — a fresh machine then inherits a
confident lie (an agent hunting for a TeX engine that isn't installed, a commit
signed by a key that doesn't exist).

Every seam is untracked, optional, and absent-safe.

| Seam file | Pulled in by | Holds |
| --- | --- | --- |
| `~/.zshrc.local` | the `~/.zshrc` stub, after the repo `zshrc` | machine PATH entries, work aliases, anything secret-adjacent |
| `~/.zshenv.local` | `~/.zshenv`, sourced last | the rare thing *every* zsh needs, scripts included — a PATH entry a script must see, proxy vars. Keep it fast; it runs on every zsh start |
| `~/.gitconfig.local` | `[include]` in `~/.gitconfig` | identity: name, email, signing key |
| `~/.ssh/config.local` | `Include` in your own `~/.ssh/config` | per-host blocks — real hostnames never enter this repo |
| `~/.vim/after/plugin/zz-local.vim` | vim's `after/plugin` load path | per-box overrides that must win over plugin defaults |
| `~/.agents/AGENTS.local.md` | shared instructions explicitly ask agents to read it when present | private or machine-specific guidance; may link into `private/agents/` |
| `~/.agents/skills.local/<name>/SKILL.md` | symlinked into both agent tools | private skills; the directory may link into `private/agents/skills/` — see `agents/SKILLS.md` |

```sh
# ~/.zshrc.local
alias deploy='…'

# ~/.zshenv.local
export PATH="$HOME/.cargo/bin:$PATH"

# ~/.gitconfig.local
[user]
	email = <you@your-domain>

# ~/.ssh/config.local
Host build
	HostName <internal-host>
	User <user>

# ~/.vim/after/plugin/zz-local.vim
let g:ale_c_cc_executable = 'gcc-15'   " no clang on this box
let g:dotfiles_author = 'Your Name'    " fills {{AUTHOR}} in vim/templates/*

# ~/.agents/AGENTS.local.md
Tectonic is installed for latex.
```

## External dependencies

`Brewfile` is annotated per package with what it backs and what degrades without
it; `Brewfile.optional` is the per-feature extras; `vim/plugins.txt` is the same
for vim. `bin/dotfiles-doctor` reports what is missing, and the troubleshooting
table in `setup.md` covers the failures that do not name their cause — a vim
whose plugin features are silently inert, or `eza` hanging in a non-TTY shell.

## Safety

- **`.gitignore` is an allowlist**: ignore everything, then re-include the
  specific tracked paths. A denylist of patterns only blocks the leaks you
  already thought of; the failure mode is a file you never meant to add
  arriving because it matched nothing.
- **gitleaks runs in CI** over the working tree and history on every push, so a
  credential cannot land unnoticed even if the allowlist is widened by mistake.
