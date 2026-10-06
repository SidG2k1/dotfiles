#!/usr/bin/env zsh
# ~/.zshenv — read by EVERY zsh invocation.
#
# Interactive shells, non-interactive shells, `zsh -c '...'`, shebang scripts,
# command substitution inside another program, coding agents' bash tools, CI
# runners: all of them read ~/.zshenv. Only ~/.zshrc is limited to interactive
# shells. So anything that must ALWAYS hold — not merely at a prompt — belongs
# here, and nothing else does: this file is on the critical path of every single
# zsh start, so keep it tiny and free of subprocesses.

# ---------------------------------------------------------------------------
# eza stdin guard  (see https://github.com/eza-community/eza/issues/1568)
# ---------------------------------------------------------------------------
# eza >= 0.23 reads paths from stdin when stdout is not a TTY. Invoked with no
# path argument in that situation it does not print the current directory and it
# does not exit: it BLOCKS FOREVER waiting on stdin (measured: still hanging at a
# two-minute timeout). Every `ls` an agent or CI job runs through this shell then
# hangs until something kills it.
#
# Two details that are easy to get wrong:
#   * The appended path is `-- .`, not `.`. eza >= 0.23 gives --icons an OPTIONAL
#     value, so `eza --icons .` is rejected with
#     "invalid value '.' for '--icons [<WHEN>]'" — the path gets eaten as the
#     flag's value. `--` ends flag parsing and makes the `.` unambiguous.
#   * Redirecting stdin from /dev/null when stdout is not a TTY means that even
#     if eza's argument handling changes again, it can never block on a terminal
#     that nobody is typing into.
#
# Guarded on the binary so that `eza` stays undefined when eza is not installed:
# a defined function would make `command -v eza` succeed everywhere and fool the
# feature tests in zshrc into aliasing ls/la/lt to a command that does not exist.
if command -v eza >/dev/null 2>&1; then
  eza() {
    local a
    # Any non-flag argument is a path (or a value for a flag); leave it alone.
    # The /dev/null still applies: a non-flag word is not always a path, so this
    # branch can still reach eza with nothing to list. `eza --level 2` is the
    # case - the 2 is the flag's value, not a path - and it hung here until the
    # redirect was added. With it, the worst case is empty output, not a shell
    # that never returns. (Write --level=2, as this repo's aliases do, and the
    # other branch appends the path.)
    for a in "$@"; do
      if [[ "$a" != -* ]]; then
        if [[ -t 1 ]]; then command eza "$@"; else command eza "$@" </dev/null; fi
        return
      fi
    done
    if [[ -t 1 ]]; then
      command eza "$@" -- .
    else
      command eza "$@" -- . </dev/null
    fi
  }
fi

# Guarded toolchain setup is also needed by scripts and agents.
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"

if [ -d "$HOME/.proto" ]; then
  export PROTO_HOME="$HOME/.proto"
  export PATH="$PROTO_HOME/shims:$PROTO_HOME/bin:$PATH"
fi

# Executable user tools must also be visible to scripts and agents.
typeset -U path
path=("$HOME/.local/bin" "$HOME/bin" $path)

# Machine-local seam for things every zsh needs (rare — PATH entries a script
# must see, proxy vars). Keep it fast; it runs for every script too.
[ -f "$HOME/.zshenv.local" ] && source "$HOME/.zshenv.local"
