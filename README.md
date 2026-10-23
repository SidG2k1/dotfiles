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
./install.sh list                    # available components; * marks saved choices
./install.sh plan shell git          # preview a selection
./install.sh install shell git       # install and remember it
bin/dotfiles-doctor                  # check this laptop's selected components
```

All components are optional except `core`, which installs the doctor helper.
The installer supplies missing packages for the components you choose, reusing
tools already on PATH. Use `--skip-brew` to provide dependencies yourself.

After a `git pull`, run `./install.sh plan`, then `./install.sh` to update the
saved selection. `install <components...>` adds choices;
`select <components...>` replaces the selection without installing anything.
Neither removes existing files or packages. Choices live in
`${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles/components`, separately on each laptop.
Copy that file if you want the same choices elsewhere, or start with a smaller
selection on a work machine.

Run `./install.sh list` for component descriptions and dependencies, or
`./install.sh --help` for command syntax. Shell integrations such as Atuin,
direnv, and Starship activate only when selected. The Claude, Codex, and OpenCode
components configure existing client installations; install and authenticate
those applications separately. GUI components such as `ghostty` and `vscode`
also install their applications through Homebrew.

Then do the parts a script cannot: `setup.md`.

## Baseten router

The local proxy and its Claude Code and OpenCode profiles are separate opt-in
components. [Set them up on another laptop](setup.md#baseten-router);
credentials stay machine-local, and the profiles preserve each client's default model.

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
`private/manifest.tsv` exists, `./install.sh install private` applies it after
the public manifest and remembers that choice. Its source paths are relative
to `private/`. Targets may overlap the public manifest for
complementary `merge-json` or `merge-toml` subsets; other targets must be distinct.
The doctor checks the private manifest and optional executable names in
`private/executables.txt` only when `private` is selected.

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
| `~/.ssh/config.local` | optional `Include` in the managed SSH block | private identity-agent settings and per-host blocks |
| `~/.vim/after/plugin/zz-local.vim` | vim's `after/plugin` load path | per-box overrides that must win over plugin defaults |
| `~/.agents/AGENTS.local.md` | shared instructions explicitly ask agents to read it when present | private or machine-specific guidance; may link into `private/agents/` |
| `~/.agents/skills.local/<name>/SKILL.md` | symlinked into selected harnesses | private skills; the directory may link into `private/agents/skills/` — see `agents/SKILLS.md` |

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

Package dependencies belong to components in `components.tsv`; Vim plugins
are listed in `vim/plugins.txt` and downloaded only with `vim-plugins`.
`bin/dotfiles-doctor` reports selected dependencies that are missing. The
troubleshooting table in `setup.md` covers less obvious failures.

## Safety

- **`.gitignore` is a denylist**: `private/`, credentials, histories, databases
  and caches are excluded; everything else is tracked. It only blocks the leaks
  it names, so review `git status` before committing.
- **Two scans run in CI**: the doctor's identity scan covers tracked files, and gitleaks covers
  every push against full history. A credential cannot land unnoticed even if it matches no ignore
  pattern.
