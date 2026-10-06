# Brewfile - required dependencies.
#
# These are the packages the tracked shell, git, and agent configs genuinely
# need. Everything here is referenced by a config file in this repo; without it
# something in this repo is broken or silently degraded. Optional extras that
# only unlock a feature live in Brewfile.optional.
#
#   brew bundle --file=Brewfile
#
# Apple Silicon assumed: zshrc sources the zsh plugins from /opt/homebrew/share.

# ls / la / ll / lt are all eza. Without it those aliases fail, and the
# FZF_ALT_C_OPTS directory preview shows an error instead of a tree.
brew "eza"

# cat is aliased to bat, and it renders the fzf Ctrl-T file preview. Without it
# both `cat` and the file picker preview break.
brew "bat"

# The Claude Code statusLine command pipes its stdin through jq, and the
# merge-json install strategies in manifest.tsv are jq merges. The status line
# guards on jq, so without it the line still shows the directory but loses the
# model name; merge-json installs cannot run at all.
brew "jq"

# Runs the Python helpers and transcription runbook. The installer reuses an
# existing uv on PATH when it is supplied outside Homebrew.
brew "uv"

# config/gh/config.yml is installed for it, and the autopush / pr-update agent
# skills drive it (`gh pr edit`, `gh pr view`). Without it that config is inert
# and both skills fail at their first command.
brew "gh"

# gitconfig sets core.pager = delta and interactive.diffFilter = delta
# --color-only, so every `git diff`, `git show`, and `git add -p` errors out
# without it. Formula name is git-delta; the binary is `delta`.
brew "git-delta"

# Ctrl-R history search, Ctrl-T file search, Alt-C directory jump (zshrc sources
# `fzf --zsh`), and the git-switch branch picker function. Without it Ctrl-R
# falls back to zsh's plain search and git-switch cannot run.
brew "fzf"

# Provides `z` for directory jumping; zshrc runs `zoxide init zsh`. Without it
# `z` does not exist (plain `cd` is unaffected).
brew "zoxide"

# Backs the FZF_DEFAULT_COMMAND / FZF_CTRL_T_COMMAND / FZF_ALT_C_COMMAND exports
# in zshrc: gitignore-aware walking for Ctrl-T and Alt-C. Without it fzf falls
# back to its built-in `find` walk, which crawls .git and node_modules.
brew "fd"

# Backs vimrc's grepprg (rg --vimgrep). Without it :grep falls back to plain
# grep; the shell itself never calls it. Formula name is ripgrep; binary is rg.
brew "ripgrep"

# SQLite-backed shell history with per-command exit code, duration, and cwd;
# zshrc runs `atuin init zsh`, which takes Ctrl-R over from fzf. Without it
# Ctrl-R stays on fzf's history search and nothing else changes.
brew "atuin"

# Renders the two-line prompt from config/starship.toml, including the
# repo-root-relative path. Without it you get zsh's default PS1.
brew "starship"

# Per-directory environment loading, hooked in zshrc. Without it .envrc files
# in project directories are silently ignored.
brew "direnv"

# The `r` alias. Without it that alias is a command-not-found.
brew "ranger"

# Inline history suggestions as you type; zshrc sources it from
# /opt/homebrew/share. Without it you lose the suggestions, nothing else.
brew "zsh-autosuggestions"

# Command-line syntax colouring; must be sourced last in zshrc so it wraps the
# vi-cursor zle widgets and fzf bindings. Without it the prompt is uncoloured.
brew "zsh-syntax-highlighting"

# Nerd Font glyphs for the starship prompt, git status symbols, and the icons in
# every eza alias. Without it those positions render as tofu boxes.
cask "font-jetbrains-mono-nerd-font"

# Smooth mouse-wheel scrolling, and a scroll direction set independently of the
# trackpad's. The exception to this file's rule: no config here reads it, and
# nothing in the repo degrades without it. It is required rather than optional
# because an external mouse is unusable on a fresh machine until it is running.
cask "mos"
