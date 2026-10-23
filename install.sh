#!/usr/bin/env bash
#
# install.sh - install this repo's configs onto a macOS machine.
#
# manifest.tsv is the source of truth: every install action below is driven by a
# row in it, and the strategy column decides HOW a target is produced. Nothing
# here hardcodes a username or a /Users/... path, and nothing writes a secret.
#
#   ./install.sh                      apply this laptop's saved selection
#   ./install.sh list                 show optional components
#   ./install.sh install shell git    install and remember components
#   ./install.sh plan                 print the plan, touch nothing
#   ./install.sh --skip-brew          leave Homebrew alone
#   ./install.sh --skip-vim-plugins   do not clone the vim plugins
#
# Re-running is safe: an already-correct target is reported and left alone. Any
# target that exists and is not already correct is backed up under
# ~/dotfiles-backup/<timestamp>/ before it is replaced, and the backup path is
# printed. Targets whose strategy is include/append-once/merge-json are never
# rewritten wholesale - only the managed block or the tracked JSON keys change.
#
# Written for the bash that ships with macOS (3.2): no associative arrays, no
# ${var,,}, no mapfile.

# shellcheck disable=SC2088
# SC2088 ("tilde does not expand in quotes") is disabled file-wide and on
# purpose. A literal '~' is *data* in this script, never a path to expand:
# manifest.tsv stores targets as '~/...' strings that are parsed, and report
# output collapses $HOME back to '~' for readability. Real expansion happens
# in one place, via "$HOME". Several of these sites are case-branch patterns,
# where a per-site directive is not valid syntax (SC1124).

set -euo pipefail

# ---------------------------------------------------------------- environment

# Repo root = directory of this script, with symlinks resolved, so the clone can
# live anywhere ($HOME/dotfiles, /opt/dotfiles, a worktree).
SCRIPT_SRC="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_SRC" ]; do
	SCRIPT_DIR_TMP="$(cd -P "$(dirname -- "$SCRIPT_SRC")" && pwd)"
	SCRIPT_SRC="$(readlink "$SCRIPT_SRC")"
	case "$SCRIPT_SRC" in
		/*) ;;
		*) SCRIPT_SRC="$SCRIPT_DIR_TMP/$SCRIPT_SRC" ;;
	esac
done
DOTFILES="$(cd -P "$(dirname -- "$SCRIPT_SRC")" && pwd)"
MANIFEST="$DOTFILES/manifest.tsv"
PLUGIN_LIST="$DOTFILES/vim/plugins.txt"
BREW_DEPENDENCIES="$DOTFILES/lib/brew-dependencies.sh"

BLOCK_START='# >>> dotfiles managed block >>>'
BLOCK_END='# <<< dotfiles managed block <<<'

BACKUP_ROOT="$HOME/dotfiles-backup/$(date +%Y%m%d-%H%M%S)"

DRY_RUN=0
SKIP_BREW=0
SKIP_VIM_PLUGINS=0

# ------------------------------------------------------------------- plumbing

if [ -t 1 ]; then
	C_RESET=$'\033[0m'; C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'
	C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_BLUE=$'\033[34m'
else
	C_RESET=""; C_DIM=""; C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BLUE=""
fi

N_OK=0
N_CHANGED=0
N_SKIPPED=0
FAILURES=()
MANUAL=()
BACKED_UP=()

heading() { printf '\n%s== %s%s\n' "$C_BOLD$C_BLUE" "$1" "$C_RESET"; }
status()  { printf '  %s%-7s%s %s\n' "$2" "$1" "$C_RESET" "$3"; }
ok()      { N_OK=$((N_OK + 1)); status ok "$C_GREEN" "$1"; }
changed() { N_CHANGED=$((N_CHANGED + 1)); status changed "$C_GREEN" "$1"; }
skipped() { N_SKIPPED=$((N_SKIPPED + 1)); status skip "$C_DIM" "$1"; }
warn()    { status warn "$C_YELLOW" "$1" >&2; }
plan()    { status plan "$C_DIM" "$1"; }
note()    {
	# Wrap a manifest note so a 300-character explanation stays readable.
	printf '%s\n' "$1" | fold -s -w 84 | while IFS= read -r _l; do
		printf '          %s%s%s\n' "$C_DIM" "$_l" "$C_RESET"
	done
}
fail() {
	# Record a failure, keep going: one broken row must not abandon the rest.
	FAILURES+=("$1")
	status FAIL "$C_RED" "$1" >&2
	if [ -n "${2:-}" ]; then note "$2" >&2; fi
}
manual() { MANUAL+=("$1"); }

die() { printf '%serror:%s %s\n' "$C_RED" "$C_RESET" "$1" >&2; exit 1; }

usage() {
	cat <<'EOF'
Usage: ./install.sh [command] [components...] [options]

  list                         show components and this laptop's selection
  install shell git claude     install and remember components (adds to selection)
  select shell git             replace selection without installing anything
  plan [components...]         preview an install, or the saved selection
  (no command)                 apply this laptop's saved selection

  --dry-run                    preview without changing files or the selection
  --only <component>           compatibility alias for install <component>
  --skip-brew                  leave package installation to you
  --skip-vim-plugins           skip plugin downloads for this run
  -h, --help                   this text

Only core (the doctor helper) is selected initially. Choices are saved locally,
never in the checkout. Removing a choice stops managing it; existing application
files and packages are not uninstalled. Use list to see component dependencies.
EOF
}

# abs_of <path> -> absolute path, resolving symlinks in the PARENT chain only.
# Used to compare "where does this existing symlink point" against "where do we
# want it to point" without depending on realpath(1) being present.
abs_of() {
	local p="$1" d b
	d="$(dirname -- "$p")"
	b="$(basename -- "$p")"
	if [ -d "$d" ]; then d="$(cd -P "$d" && pwd)"; fi
	case "$b" in
		.)  printf '%s\n' "$d" ;;
		..) printf '%s\n' "$(dirname -- "$d")" ;;
		*)  printf '%s/%s\n' "${d%/}" "$b" ;;
	esac
}

# display_path <abs path> -> the same path written with a leading ~ when it is
# under $HOME, so printed output and generated files carry no username.
display_path() {
	case "$1" in
		"$HOME") printf '~\n' ;;
		"$HOME"/*) printf '~/%s\n' "${1#"$HOME"/}" ;;
		*) printf '%s\n' "$1" ;;
	esac
}

# shell_path <abs path> -> the path written for embedding in a generated shell
# file: "$HOME/dotfiles/zshrc" rather than an absolute /Users/... string.
shell_path() {
	case "$1" in
		"$HOME"/*) printf '$HOME/%s\n' "${1#"$HOME"/}" ;;
		*) printf '%s\n' "$1" ;;
	esac
}

expand_target() {
	case "$1" in
		"~/"*) printf '%s/%s\n' "$HOME" "${1#\~/}" ;;
		"~") printf '%s\n' "$HOME" ;;
		*) printf '%s\n' "$1" ;;
	esac
}

want_group() {
	[ "$1" = never ] && return 0
	[ "$1" = vim-plugins ] && [ "$SKIP_VIM_PLUGINS" -eq 1 ] && return 1
	case " $COMPONENT_ACTIVE " in *" $1 "*) return 0 ;; esac
	return 1
}

ensure_dir() {
	local d="$1" mode="${2:-}"
	if [ -d "$d" ]; then
		if [ -n "$mode" ] && [ "$DRY_RUN" -eq 0 ]; then chmod "$mode" "$d"; fi
		return 0
	fi
	if [ -e "$d" ] || [ -L "$d" ]; then
		fail "$(display_path "$d") exists and is not a directory" \
			"Move or remove it by hand, then re-run. The installer will not delete a non-directory that is in the way of a directory."
		return 1
	fi
	if [ "$DRY_RUN" -eq 1 ]; then
		plan "mkdir -p $(display_path "$d")${mode:+ (mode $mode)}"
		return 0
	fi
	mkdir -p "$d"
	if [ -n "$mode" ]; then chmod "$mode" "$d"; fi
	return 0
}

ensure_parent() {
	local d
	d="$(dirname -- "$1")"
	case "$d" in
		"$HOME/.gnupg") ensure_dir "$d" 700 ;;  # gpg refuses a world-readable ~/.gnupg
		*) ensure_dir "$d" ;;
	esac
}

# backup_dest <target> -> a path under $BACKUP_ROOT that mirrors the target's
# location relative to $HOME, so the backup is self-describing.
backup_dest() {
	local t="$1" rel
	case "$t" in
		"$HOME"/*) rel="${t#"$HOME"/}" ;;
		/*) rel="ROOT/${t#/}" ;;
		*) rel="$t" ;;
	esac
	local dest="$BACKUP_ROOT/$rel" n=1
	while [ -e "$dest" ] || [ -L "$dest" ]; do
		dest="$BACKUP_ROOT/$rel.$n"
		n=$((n + 1))
	done
	printf '%s\n' "$dest"
}

# backup_move: for strategies that REPLACE the target (link, wrap). Moving is
# used rather than copy+delete so nothing can be lost to a partial copy.
backup_move() {
	local t="$1" dest
	dest="$(backup_dest "$t")"
	if [ "$DRY_RUN" -eq 1 ]; then
		plan "backup (move) $(display_path "$t") -> $(display_path "$dest")"
		return 0
	fi
	mkdir -p "$(dirname -- "$dest")"
	mv "$t" "$dest"
	status backup "$C_YELLOW" "$(display_path "$t") -> $(display_path "$dest")"
	BACKED_UP+=("$(display_path "$dest")")
}

# backup_copy: for strategies that EDIT the target in place (include,
# append-once, merge-json). The target has to stay where it is.
backup_copy() {
	local t="$1" dest
	dest="$(backup_dest "$t")"
	if [ "$DRY_RUN" -eq 1 ]; then
		plan "backup (copy) $(display_path "$t") -> $(display_path "$dest")"
		return 0
	fi
	mkdir -p "$(dirname -- "$dest")"
	cp -Rp "$t" "$dest"
	status backup "$C_YELLOW" "$(display_path "$t") -> $(display_path "$dest")"
	BACKED_UP+=("$(display_path "$dest")")
}

TMPDIR_SELF=""
tmpfile() {
	if [ -z "$TMPDIR_SELF" ]; then
		TMPDIR_SELF="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-install.XXXXXX")"
	fi
	mktemp "$TMPDIR_SELF/f.XXXXXX"
}
cleanup() { if [ -n "$TMPDIR_SELF" ]; then rm -rf "$TMPDIR_SELF"; fi; }
trap cleanup EXIT

# Write $1 (a temp file) over $2 (the real target), keeping the target's own
# mode when it already exists. Writing through with `cat` rather than `cp` so an
# existing file keeps its inode, mode and ownership; only a file we create gets
# a mode of ours.
install_content() {
	local src="$1" tgt="$2" existed=0
	if [ "$DRY_RUN" -eq 1 ]; then return 0; fi
	if [ -e "$tgt" ]; then existed=1; fi
	cat "$src" >"$tgt"
	if [ "$existed" -eq 0 ]; then chmod 644 "$tgt"; fi
}

# The in-place strategies (include, append-once, merge-json) edit the target
# where it stands. If the target is a leftover symlink INTO this repo - what an
# older link-everything install would have left - editing in place would write
# into the repo working tree instead (and for ~/.gitconfig, produce a file that
# includes itself). Move that link aside and start from a real file. A symlink
# pointing anywhere else is the user's own indirection and is honoured.
detach_repo_symlink() {
	local tgt="$1" cur cur_abs
	[ -L "$tgt" ] || return 0
	cur="$(readlink "$tgt")"
	case "$cur" in
		/*) cur_abs="$(abs_of "$cur")" ;;
		*) cur_abs="$(abs_of "$(dirname -- "$tgt")/$cur")" ;;
	esac
	case "$cur_abs" in
		"$DOTFILES"/*|"$DOTFILES")
			warn "$(display_path "$tgt") is a symlink into the repo; this strategy needs a real file"
			backup_move "$tgt"
			;;
	esac
	return 0
}

# ------------------------------------------------------------ argument parsing

[ -f "$DOTFILES/lib/components.sh" ] || die "component helpers are missing"
# shellcheck source=lib/components.sh
. "$DOTFILES/lib/components.sh"
ACTION=apply
REQUESTED=
while [ $# -gt 0 ]; do
	case "$1" in
		--dry-run) DRY_RUN=1 ;;
		--skip-brew) SKIP_BREW=1 ;;
		--skip-vim-plugins) SKIP_VIM_PLUGINS=1 ;;
		--only)
			[ $# -ge 2 ] || die "--only needs a component name"
			[ -n "$2" ] || die "--only needs a component name"
			ACTION=install; REQUESTED="$REQUESTED $2"; shift ;;
		--only=*)
			[ -n "${1#--only=}" ] || die "--only needs a component name"
			ACTION=install; REQUESTED="$REQUESTED ${1#--only=}" ;;
		list|install|select|plan)
			[ "$ACTION" = apply ] || die "choose one command"
			ACTION=$1 ;;
		-h|--help) usage; exit 0 ;;
		-*) die "unknown option '$1'; see --help" ;;
		*)
			[ "$ACTION" != apply ] || ACTION=install
			REQUESTED="$REQUESTED $1" ;;
	esac
	shift
done

[ -f "$MANIFEST" ] || die "manifest.tsv is missing"
[ -f "$COMPONENT_CATALOG" ] || die "components.tsv is missing"
[ -f "$BREW_DEPENDENCIES" ] || die "dependency probes are missing"
# shellcheck source=lib/brew-dependencies.sh
. "$BREW_DEPENDENCIES"
if [ "$ACTION" = select ]; then COMPONENT_SAVED=core; else components_read || exit 1; fi
components_resolve "$COMPONENT_SAVED" || exit 1
COMPONENT_SELECTED=$COMPONENT_RESOLVED

if [ "$ACTION" = list ]; then
	[ -z "$REQUESTED" ] || die "list does not take component names"
	printf '  %-18s %-62s %s\n' COMPONENT DESCRIPTION REQUIRES
	while IFS=$'\t' read -r name description requires _formulae _casks; do
		case "$name" in ''|'#'*) continue ;; esac
		mark=' '; component_enabled "$name" && mark='*'
		printf '%s %-18s %-62s %s\n' "$mark" "$name" "$description" "$requires"
	done <"$COMPONENT_CATALOG"
	printf '\n* selected on this laptop. Selection: %s\n' "$COMPONENT_SELECTION_FILE"
	exit 0
fi
if [ "$ACTION" = select ]; then
	components_resolve "$REQUESTED" || exit 1
	COMPONENT_SELECTED=$COMPONENT_RESOLVED
	if [ "$DRY_RUN" -eq 0 ]; then components_save; fi
	printf 'Selection%s: %s\n' "$([ "$DRY_RUN" -eq 1 ] && printf ' preview')" "$COMPONENT_SELECTED"
	printf 'Run ./install.sh to apply. Existing files and packages are left in place.\n'
	exit 0
fi
if [ "$ACTION" = install ] && [ -z "$REQUESTED" ]; then die "name components to install (see list)"; fi
[ "$ACTION" != plan ] || DRY_RUN=1
if [ -z "$REQUESTED" ]; then REQUESTED=$COMPONENT_SAVED; fi
components_resolve "$REQUESTED" || exit 1
COMPONENT_ACTIVE=$COMPONENT_RESOLVED
components_resolve "$COMPONENT_SAVED $COMPONENT_ACTIVE" || exit 1
COMPONENT_SELECTED=$COMPONENT_RESOLVED

# ------------------------------------------------------------------ strategies

# The link value for a row. Some rows deliberately do NOT point at the repo:
#   * ~/.claude/CLAUDE.md, ~/.codex/AGENTS.md and ~/.config/opencode/AGENTS.md
#     point at ~/.agents/AGENTS.md so all four agents read one file and the
#     repo can move.
#   * each skills dir's README.md is a RELATIVE ../../.agents/SKILLS.md link,
#     the same shape as the skill links phase_agent_extras writes.
link_value_for() {
	local src_rel="$1" src_abs="$2" tgt="$3"
	case "$tgt" in
		"$HOME/.claude/skills/README.md"|"$HOME/.codex/skills/README.md")
			printf '../../.agents/SKILLS.md\n'
			return 0
			;;
	esac
	if [ "$src_rel" = "agents/AGENTS.md" ] && [ "$tgt" != "$HOME/.agents/AGENTS.md" ]; then
		printf '%s\n' "$HOME/.agents/AGENTS.md"
		return 0
	fi
	printf '%s\n' "$src_abs"
}

do_link() {
	local src_rel="$1" src_abs="$2" tgt="$3"
	local want want_abs cur cur_abs

	want="$(link_value_for "$src_rel" "$src_abs" "$tgt")"
	case "$want" in
		/*) want_abs="$(abs_of "$want")" ;;
		*) want_abs="$(abs_of "$(dirname -- "$tgt")/$want")" ;;
	esac

	# The ~/.claude and ~/.codex links point through ~/.agents, which an earlier
	# manifest row creates - so in a dry run "not there yet" is expected and not
	# worth warning about.
	if [ ! -e "$want_abs" ] && [ "$DRY_RUN" -eq 0 ]; then
		warn "$(display_path "$tgt") points at $(display_path "$want_abs"), which does not exist"
	fi

	ensure_parent "$tgt" || return 0

	if [ -L "$tgt" ]; then
		cur="$(readlink "$tgt")"
		if [ "$cur" = "$want" ]; then
			ok "$(display_path "$tgt") -> $want"
			return 0
		fi
		case "$cur" in
			/*) cur_abs="$(abs_of "$cur")" ;;
			*) cur_abs="$(abs_of "$(dirname -- "$tgt")/$cur")" ;;
		esac
		if [ "$cur_abs" = "$want_abs" ]; then
			# Same file, different spelling (absolute vs relative). Normalise
			# quietly; nothing is at risk, so no backup.
			if [ "$DRY_RUN" -eq 1 ]; then
				plan "relink $(display_path "$tgt") -> $want (was $cur)"
			else
				ln -sfn "$want" "$tgt"
				changed "$(display_path "$tgt") -> $want (normalised from $cur)"
			fi
			return 0
		fi
		backup_move "$tgt"
	elif [ -e "$tgt" ]; then
		backup_move "$tgt"
	fi

	if [ "$DRY_RUN" -eq 1 ]; then
		plan "link $(display_path "$tgt") -> $want"
		return 0
	fi
	ln -sfn "$want" "$tgt"
	changed "$(display_path "$tgt") -> $want"
}

# wrap: the target becomes a stub that sources the repo file and then the
# machine-local tail. The repo file stays public; PATH entries, work aliases and
# anything secret-adjacent live in the .local file, which is never tracked.
do_wrap() {
	local src_abs="$1" tgt="$2"
	local localfile="${tgt}.local" tmp
	tmp="$(tmpfile)"

	{
		printf '# Managed by dotfiles install.sh - regenerated on every run, do not edit.\n'
		printf '# Repo config:   %s\n' "$(display_path "$src_abs")"
		printf '# Machine-local: %s (untracked, optional, sourced last)\n' "$(display_path "$localfile")"
		printf 'source "%s"\n' "$(shell_path "$src_abs")"
		printf '[ -r "%s" ] && source "%s"\n' "$(shell_path "$localfile")" "$(shell_path "$localfile")"
		printf ':\n'
	} >"$tmp"

	ensure_parent "$tgt" || return 0

	if [ -f "$tgt" ] && [ ! -L "$tgt" ] && cmp -s "$tmp" "$tgt"; then
		ok "$(display_path "$tgt") stub (sources $(display_path "$src_abs"), then $(display_path "$localfile"))"
		return 0
	fi

	if [ -e "$tgt" ] || [ -L "$tgt" ]; then
		backup_move "$tgt"
		manual "Your previous $(display_path "$tgt") was backed up - move any machine-specific lines from it into $(display_path "$localfile") (that file is untracked and sourced last)."
	fi

	if [ "$DRY_RUN" -eq 1 ]; then
		plan "write stub $(display_path "$tgt") -> sources $(display_path "$src_abs"), then $(display_path "$localfile")"
		return 0
	fi
	install_content "$tmp" "$tgt"
	changed "$(display_path "$tgt") stub written"
}

# include: the target stays user-owned. We append [include] directives and never
# touch anything else, because ~/.gitconfig holds identity (user.email,
# user.signingkey) and tool-written blocks like [filter "lfs"].
gitconfig_has_include() {
	local file="$1" want_abs="$2" line
	[ -f "$file" ] || return 1
	while IFS= read -r line; do
		case "$line" in "~/"*) line="$HOME/${line#\~/}" ;; esac
		[ "$line" = "$want_abs" ] && return 0
	done <<EOF
$(git config --file "$file" --get-all include.path 2>/dev/null || true)
EOF
	return 1
}

do_include() {
	local src_abs="$1" tgt="$2"
	local localcfg="$HOME/.gitconfig.local"
	# Two include paths, tracked in two scalars rather than a list, so a repo
	# path containing a space cannot be split apart.
	local pend_repo="" pend_local=""

	ensure_parent "$tgt" || return 0
	detach_repo_symlink "$tgt"

	if gitconfig_has_include "$tgt" "$src_abs"; then
		ok "$(display_path "$tgt") already includes $(display_path "$src_abs")"
	else
		pend_repo="$src_abs"
	fi
	if gitconfig_has_include "$tgt" "$localcfg"; then
		ok "$(display_path "$tgt") already includes $(display_path "$localcfg")"
	else
		pend_local="$localcfg"
	fi

	if [ -n "$pend_repo" ] || [ -n "$pend_local" ]; then
		if [ -f "$tgt" ]; then backup_copy "$tgt"; fi
		if [ "$DRY_RUN" -eq 1 ]; then
			if [ -n "$pend_repo" ]; then
				plan "append [include] path = $(display_path "$pend_repo") to $(display_path "$tgt")"
			fi
			if [ -n "$pend_local" ]; then
				plan "append [include] path = $(display_path "$pend_local") to $(display_path "$tgt")"
			fi
		else
			# Guarantee we start on a fresh line; never rewrite existing bytes.
			if [ -s "$tgt" ] && [ -n "$(tail -c 1 "$tgt")" ]; then printf '\n' >>"$tgt"; fi
			{
				printf '\n# Added once by dotfiles install.sh. Everything else in this file is yours.\n'
				[ -n "$pend_repo" ] && printf '[include]\n\tpath = %s\n' "$(display_path "$pend_repo")"
				[ -n "$pend_local" ] && printf '[include]\n\tpath = %s\n' "$(display_path "$pend_local")"
				:
			} >>"$tgt"
			if [ -n "$pend_repo" ]; then
				changed "$(display_path "$tgt") includes $(display_path "$pend_repo")"
			fi
			if [ -n "$pend_local" ]; then
				changed "$(display_path "$tgt") includes $(display_path "$pend_local")"
			fi
		fi
	fi

	# Identity lives in the untracked .local file. Seed a commented template
	# only - this script never writes an email address or a key.
	if [ ! -e "$localcfg" ]; then
		if [ "$DRY_RUN" -eq 1 ]; then
			plan "create $(display_path "$localcfg") (commented identity template)"
		else
			{
				printf '# Machine-local git identity. Untracked on purpose: nothing here is public.\n'
				printf '# Included by %s.\n' "$(display_path "$tgt")"
				printf '[user]\n'
				printf '\t# name = <your name>\n'
				printf '\t# email = <your address>\n'
			} >"$localcfg"
			chmod 600 "$localcfg"
			changed "$(display_path "$localcfg") created (fill in identity)"
		fi
		manual "Fill in $(display_path "$localcfg") with [user] name and email. The tracked gitconfig sets no identity and no commit signing - both are machine-specific."
	else
		ok "$(display_path "$localcfg") exists (identity left untouched)"
	fi
}

# append-once: both the tool and the human edit this file, so the repo owns only
# the region between the markers and rewrites just that.
do_append_once() {
	local src_abs="$1" tgt="$2"
	local block desired

	block="$(tmpfile)"
	{
		printf '%s\n' "$BLOCK_START"
		printf '# Generated from %s by dotfiles install.sh.\n' "$(display_path "$src_abs")"
		printf '# Edits between these markers are overwritten - put yours outside them.\n'
		cat "$src_abs"
		printf '%s\n' "$BLOCK_END"
	} >"$block"

	ensure_parent "$tgt" || return 0
	detach_repo_symlink "$tgt"

	desired="$(tmpfile)"
	if [ -f "$tgt" ]; then
		local has_start=0 has_end=0
		if grep -Fxq "$BLOCK_START" "$tgt"; then has_start=1; fi
		if grep -Fxq "$BLOCK_END" "$tgt"; then has_end=1; fi
		if [ "$has_start" -eq 1 ] && [ "$has_end" -eq 0 ]; then
			fail "$(display_path "$tgt") has an opening managed marker with no closing one" \
				"Refusing to touch it: replacing the block would silently delete everything after the marker. Add the line '$BLOCK_END' at the end of the managed region (or delete the opening marker), then re-run."
			return 0
		fi
		awk -v s="$BLOCK_START" -v e="$BLOCK_END" -v bf="$block" '
			$0 == s { found = 1; inb = 1
				while ((getline l < bf) > 0) print l
				close(bf); next }
			inb && $0 == e { inb = 0; next }
			inb { next }
			{ print }
			END {
				if (!found) {
					if (NR > 0) print ""
					while ((getline l < bf) > 0) print l
					close(bf)
				}
			}
		' "$tgt" >"$desired"
	else
		cat "$block" >"$desired"
	fi

	if [ -f "$tgt" ] && cmp -s "$desired" "$tgt"; then
		ok "$(display_path "$tgt") managed block up to date"
		return 0
	fi

	if [ -f "$tgt" ]; then backup_copy "$tgt"; fi
	if [ "$DRY_RUN" -eq 1 ]; then
		plan "write managed block into $(display_path "$tgt") (rest of the file untouched)"
		return 0
	fi
	install_content "$desired" "$tgt"
	changed "$(display_path "$tgt") managed block written"
}

# merge-json: the app writes this file itself, so merge the tracked key subset
# instead of linking. The tracked subset is exactly the top-level keys present
# in the repo file; the merge is recursive (jq's `*`), so nested keys the app
# added survive and only tracked keys are overwritten. A merge cannot delete: a
# key the repo drops lingers in the target until removed by hand.
do_merge_json() {
	local src_abs="$1" tgt="$2"
	local desired

	if ! command -v jq >/dev/null 2>&1; then
		fail "jq is required to merge $(display_path "$tgt") and is not on PATH" \
			"Install it with 'brew install jq' or re-run without --skip-brew."
		return 0
	fi
	if ! jq -e . "$src_abs" >/dev/null 2>&1; then
		fail "$(display_path "$src_abs") is not valid JSON" \
			"Fix the repo file; the installer will not merge a file it cannot parse."
		return 0
	fi

	ensure_parent "$tgt" || return 0
	detach_repo_symlink "$tgt"

	desired="$(tmpfile)"

	if [ -f "$tgt" ]; then
		if [ ! -r "$tgt" ]; then
			fail "$(display_path "$tgt") is not readable"
			return 0
		fi
		if ! jq -e . "$tgt" >/dev/null 2>&1; then
			fail "$(display_path "$tgt") is not valid JSON - not merging" \
				"Nothing was written and nothing was removed. Most often this is JSONC: comments or trailing commas, which VS Code accepts and jq does not. Strip them (or move the file aside) and re-run."
			return 0
		fi
		if ! jq -s '.[0] * .[1]' "$tgt" "$src_abs" >"$desired" 2>/dev/null; then
			fail "jq merge failed for $(display_path "$tgt")"
			return 0
		fi
	else
		if ! jq '.' "$src_abs" >"$desired" 2>/dev/null; then
			fail "jq could not render $(display_path "$src_abs")"
			return 0
		fi
	fi

	if ! jq -e . "$desired" >/dev/null 2>&1; then
		fail "refusing to write $(display_path "$tgt"): merged result is not valid JSON"
		return 0
	fi

	# Compare semantically so a difference in the app's own indentation does not
	# cause a rewrite on every run.
	if [ -f "$tgt" ] && jq -e -s '.[0] == .[1]' "$tgt" "$desired" >/dev/null 2>&1; then
		ok "$(display_path "$tgt") tracked keys already merged"
		return 0
	fi

	if [ -f "$tgt" ]; then backup_copy "$tgt"; fi
	if [ "$DRY_RUN" -eq 1 ]; then
		plan "jq-merge tracked keys of $(display_path "$src_abs") into $(display_path "$tgt")"
		return 0
	fi
	install_content "$desired" "$tgt"
	changed "$(display_path "$tgt") tracked keys merged"
}

do_merge_toml() {
	local src_abs="$1" tgt="$2" desired
	local helper="$DOTFILES/lib/merge-toml.py"
	ensure_parent "$tgt" || return 0
	detach_repo_symlink "$tgt"
	desired="$(tmpfile)"
	if command -v uv >/dev/null 2>&1; then
		if ! uv run --no-project --python '>=3.11' python "$helper" "$src_abs" "$tgt" >"$desired"; then
			fail "TOML merge failed for $(display_path "$tgt")"; return 0
		fi
	else
		fail "merge-toml requires uv"; return 0
	fi
	if [ -f "$tgt" ] && cmp -s "$desired" "$tgt"; then
		ok "$(display_path "$tgt") tracked TOML preferences already merged"; return 0
	fi
	if [ -f "$tgt" ]; then backup_copy "$tgt"; fi
	if [ "$DRY_RUN" -eq 1 ]; then
		plan "merge tracked TOML preferences into $(display_path "$tgt")"
	else
		install_content "$desired" "$tgt"
		changed "$(display_path "$tgt") tracked TOML preferences merged"
	fi
}

do_never() {
	local tgt="$1" note_text="$2"
	skipped "$(display_path "$tgt") - not installed by this repo"
	if [ -n "$note_text" ]; then note "$note_text"; fi
}

# ---------------------------------------------------------------------- phases

phase_dirs() {
	heading "directories"
	ensure_dir "$HOME/bin"
	if want_group vim; then
		local d
		for d in backup swap undo after/plugin; do ensure_dir "$HOME/.vim/$d"; done
	fi
	if want_group skills; then ensure_dir "$HOME/.agents/skills"; fi
	if want_group claude; then ensure_dir "$HOME/.claude/skills"; fi
	if want_group codex; then ensure_dir "$HOME/.codex/skills"; fi
}

phase_brew() {
	local kind name
	heading "selected dependencies"
	while IFS=$'\t' read -r kind name; do
		[ -n "$name" ] || continue
		if pkg_present "$kind" "$name"; then
			ok "$kind $name (available)"
		elif [ "$DRY_RUN" -eq 1 ]; then
			plan "brew install $([ "$kind" = cask ] && printf '%s ' --cask)$name"
		elif ! command -v brew >/dev/null 2>&1; then
			fail "Missing $name; install Homebrew or provide the dependency yourself."
		elif [ "$kind" = cask ] && brew install --cask "$name" </dev/null; then
			changed "$name installed"
		elif [ "$kind" = brew ] && brew install "$name" </dev/null; then
			changed "$name installed"
		else
			fail "Could not install $name"
		fi
	done < <(components_packages "$COMPONENT_ACTIVE")
}

phase_manifest() {
	heading "manifest"
	local manifest_file=${1:-$MANIFEST} source_root=${2:-$DOTFILES}
	local group=${3:-core} src tgt strat note_text src_abs

	# Read the manifest on fd 3 so nothing inside the loop (git, curl, brew, jq)
	# can swallow the rest of the file by reading stdin.
	while IFS=$'\t' read -r src tgt strat note_text <&3 || [ -n "${src:-}" ]; do
		# A private manifest is one component; its headers are cosmetic.
		case "$src" in
			'# ---- '*' ----'*)
				if [ -z "${3:-}" ]; then
					group="${src#\# ---- }"
					group="${group%% ----*}"
				fi
				continue
				;;
			''|'#'*) continue ;;
		esac
		[ -n "${strat:-}" ] || continue
		want_group "$group" || continue

		tgt="$(expand_target "$tgt")"
		src_abs="$source_root/$src"
		case "$src" in /*|../*|*/../*|*/..) fail "manifest source must stay inside its layer: $src"; continue ;; esac

		case "$strat" in
			never)
				do_never "$tgt" "${note_text:-}"
				continue
				;;
		esac

		if [ ! -e "$src_abs" ]; then
			fail "manifest row '$src' -> $(display_path "$tgt"): source file is missing from the repo" \
				"Either the file has not been committed yet or the manifest path is wrong. Nothing was written for this row; every other row still ran."
			continue
		fi

		case "$strat" in
			link) do_link "$src" "$src_abs" "$tgt" ;;
			wrap) do_wrap "$src_abs" "$tgt" ;;
			include) do_include "$src_abs" "$tgt" ;;
			append-once) do_append_once "$src_abs" "$tgt" ;;
			merge-json) do_merge_json "$src_abs" "$tgt" ;;
			merge-toml) do_merge_toml "$src_abs" "$tgt" ;;
			*)
				fail "unknown strategy '$strat' for $src -> $(display_path "$tgt")" \
					"Valid strategies: link, wrap, include, append-once, merge-json, merge-toml, never."
				;;
		esac
	done 3<"$manifest_file"
	return 0
}

phase_vim_plugins() {
	heading "vim plugins"
	# Native vim packages: vim 8+ loads everything under pack/*/start/ itself
	# (:help packages), so cloning into this directory is the whole install.
	local bundle="$HOME/.vim/pack/bundle/start"
	local repo dest

	ensure_dir "$bundle" || return 0

	if [ ! -f "$PLUGIN_LIST" ]; then
		fail "$(display_path "$PLUGIN_LIST") not found; no bundles installed"
		return 0
	fi
	if ! command -v git >/dev/null 2>&1; then
		fail "git not found; cannot clone vim bundles" \
			"Install the Xcode Command Line Tools (xcode-select --install) and re-run."
		return 0
	fi

	while IFS= read -r repo <&4 || [ -n "${repo:-}" ]; do
		repo="${repo%%#*}"
		repo="$(printf '%s' "$repo" | tr -d '\r' | tr -d '[:space:]')"
		[ -n "$repo" ] || continue
		if printf '%s' "$repo" | grep -qv '^[A-Za-z0-9._-]\{1,\}/[A-Za-z0-9._-]\{1,\}$'; then
			fail "vim/plugins.txt: '$repo' is not an owner/repo line"
			continue
		fi
		dest="$bundle/${repo##*/}"
		if [ -e "$dest" ]; then
			ok "$(display_path "$dest") (present; update it yourself with git -C pull)"
			continue
		fi
		if [ "$DRY_RUN" -eq 1 ]; then
			plan "git clone --depth 1 https://github.com/$repo -> $(display_path "$dest")"
			continue
		fi
		if git clone --quiet --depth 1 "https://github.com/$repo" "$dest" </dev/null; then
			changed "$(display_path "$dest") cloned"
		else
			fail "clone failed for $repo" \
				"Re-run: git clone --depth 1 https://github.com/$repo $(display_path "$dest"). The vimrc settings that plugin backs will silently do nothing until it is present."
		fi
	done 4<"$PLUGIN_LIST"
	return 0
}

link_agent_skills() { # link_agent_skills <layer>... - dirs under ~/.agents
	local layer dir name tool target
	# Relative links, so ~/.agents and both tool dirs resolve to one SKILL.md.
	for layer in "$@"; do
		for dir in "$HOME/.agents/$layer"/*/; do
			[ -d "$dir" ] || continue
			name="$(basename -- "$dir")"
			for tool in claude codex; do
				component_enabled "$tool" || continue
				target="$HOME/.$tool/skills/$name"
				if [ -e "$target" ] || [ -L "$target" ]; then
					ok "$(display_path "$target")"
				elif [ "$DRY_RUN" -eq 1 ]; then
					plan "ln -s ../../.agents/$layer/$name $(display_path "$target")"
				else
					ensure_parent "$target" || continue
					ln -s "../../.agents/$layer/$name" "$target"
					changed "$(display_path "$target") -> ../../.agents/$layer/$name"
				fi
			done
		done
	done
}

phase_agent_extras() {
	heading "agent skills + gh extension"
	local spec name
	for spec in $VENDORED_SKILLS; do
		name="${spec##*@}"
		if [ -d "$HOME/.agents/skills/$name" ]; then
			ok "vendored skill $name present"
		elif [ "$DRY_RUN" -eq 1 ]; then
			plan "npx -y skills add $spec -g --agent universal -y"
		elif ! command -v npx >/dev/null 2>&1; then
			fail "npx not found; provide Node.js and re-run agent-extras"
		elif npx -y skills add "$spec" -g --agent universal -y </dev/null; then
			changed "vendored skill $name installed from $spec"
		else
			fail "skills CLI could not install $name" \
				"Re-run by hand: npx -y skills add $spec -g --agent universal -y"
		fi
	done


	if ! command -v gh >/dev/null 2>&1; then
		fail "gh not found; provide GitHub CLI and re-run agent-extras"
	elif gh extension list 2>/dev/null | grep -q 'github/gh-stack'; then
		ok "gh extension gh-stack"
	elif [ "$DRY_RUN" -eq 1 ]; then
		plan "gh extension install github/gh-stack"
	elif gh extension install github/gh-stack </dev/null; then
		changed "gh extension gh-stack installed"
	else
		fail "gh extension install github/gh-stack failed (gh not authenticated?)"
		manual "Run 'gh auth login', then: gh extension install github/gh-stack"
	fi
	return 0
}

phase_mermaid() {
	local directory="$HOME/.local/share/dotfiles/mermaid"
	if [ -x "$directory/node_modules/.bin/mmdc" ]; then
		ok "Mermaid CLI available"
	elif [ "$DRY_RUN" -eq 1 ]; then
		plan "npm install --prefix $(display_path "$directory")"
	elif command -v npm >/dev/null 2>&1 && npm install --prefix "$directory" </dev/null; then
		changed "Mermaid CLI installed"
	else
		fail "Mermaid setup needs npm; provide Node.js and re-run."
	fi
}

# ----------------------------------------------------------------------- main

printf 'dotfiles install  repo: %s\n' "$(display_path "$DOTFILES")"
printf 'components: %s\n' "$COMPONENT_ACTIVE"
[ "$DRY_RUN" -eq 0 ] || printf 'dry run: files, packages, and saved selection are unchanged.\n'
if [ ! -f "$COMPONENT_SELECTION_FILE" ] && [ "$ACTION" = apply ]; then
	printf 'No laptop selection yet. Use ./install.sh list, then ./install.sh install <components...>.\n'
fi
phase_dirs
if [ "$SKIP_BREW" -eq 1 ]; then skipped "dependency installation (--skip-brew)"; else phase_brew; fi
if want_group package-safety && [ "$DRY_RUN" -eq 0 ]; then
	# shellcheck source=lib/package-safety.sh
	. "$DOTFILES/lib/package-safety.sh"
	package_script_approvals_supported || die "Update the package managers before enabling package-safety."
	uv --config-file "$DOTFILES/config/package-safety/uv.toml" tool list >/dev/null ||
		die "Update uv with its original installation method before enabling package-safety."
fi
phase_manifest
if want_group package-safety; then
	# shellcheck source=lib/package-safety.sh
	. "$DOTFILES/lib/package-safety.sh"
	if [ "$DRY_RUN" -eq 1 ]; then
		plan "apply pnpm security settings through its CLI, if installed"
	elif pnpm_security_config apply; then
		ok "pnpm security settings applied (if installed)"
	else
		fail "Could not apply pnpm security settings"
	fi
fi
if want_group private; then
	if [ -f "$DOTFILES/private/manifest.tsv" ]; then
		phase_manifest "$DOTFILES/private/manifest.tsv" "$DOTFILES/private" private
	else
		fail "private selected, but private/manifest.tsv is missing on this laptop"
	fi
fi
if want_group agent-extras; then phase_agent_extras; fi
if want_group skills || want_group claude || want_group codex || want_group agent-extras || want_group private; then
	link_agent_skills skills skills.local
fi
if want_group vim-plugins; then phase_vim_plugins; fi
if want_group mermaid; then phase_mermaid; fi
if [ "$DRY_RUN" -eq 0 ] && [ "${#FAILURES[@]}" -eq 0 ]; then components_save; fi

# ------------------------------------------------------------------- epilogue

heading "summary"
printf '  %d ok, %d changed, %d skipped, %d failed\n' \
	"$N_OK" "$N_CHANGED" "$N_SKIPPED" "${#FAILURES[@]}"
if [ ${#BACKED_UP[@]} -gt 0 ]; then
	printf '  backups: %s\n' "$(display_path "$BACKUP_ROOT")"
fi

heading "still to do by hand"
i=1
say_step() { printf '  %d. %s\n' "$i" "$1"; i=$((i + 1)); }

say_step "Identity, auth, GUI permission grants and the other human-only steps: setup.md, section 3 onward."
if [ ${#BACKED_UP[@]} -gt 0 ]; then
	say_step "Review what was moved aside in $(display_path "$BACKUP_ROOT") and fold anything machine-specific into the matching .local seam. Nothing was deleted."
fi
if [ ${#MANUAL[@]} -gt 0 ]; then
	for m in "${MANUAL[@]}"; do
		say_step "$m"
	done
fi
if want_group shell; then say_step "Open a new terminal to load the selected shell integrations."; fi

if [ ${#FAILURES[@]} -gt 0 ]; then
	printf '\n%s%d step(s) failed:%s\n' "$C_RED" "${#FAILURES[@]}" "$C_RESET" >&2
	for f in "${FAILURES[@]}"; do
		printf '  - %s\n' "$f" >&2
	done
	printf '\nEverything else was installed. Fix the above and re-run - this script is idempotent.\n' >&2
	exit 1
fi

printf '\n%sdone.%s\n' "$C_GREEN" "$C_RESET"
