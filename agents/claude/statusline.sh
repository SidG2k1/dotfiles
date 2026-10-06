#!/usr/bin/env bash
# Claude Code statusLine: reads the session JSON on stdin, prints one line.
# Colours follow config/starship.toml. Runs on every render, so anything slow
# (gh) is cached and refreshed in the background.
set -u

sep=$'\x1f'
input=$(cat)

IFS=$sep read -r model effort cwd wt ctx rl5 rl5_reset rl7 added removed < <(
	printf '%s' "$input" | jq -r --arg sep "$sep" '
		def pct: if . == null then "" else (. + 0.5 | floor | tostring) end;
		[ .model.display_name // "",
		  .effort.level // "",
		  .workspace.current_dir // .cwd // "",
		  .worktree.name // "",
		  (.context_window.used_percentage | pct),
		  (.rate_limits.five_hour.used_percentage | pct),
		  (.rate_limits.five_hour.resets_at // "" | tostring),
		  (.rate_limits.seven_day.used_percentage | pct),
		  (.cost.total_lines_added // 0 | tostring),
		  (.cost.total_lines_removed // 0 | tostring)
		] | join($sep)' 2>/dev/null
)
[ -n "${cwd:-}" ] || cwd=$PWD

RESET=$'\e[0m' DIM=$'\e[2m' BLUE=$'\e[34m' YELLOW=$'\e[33m' MAGENTA=$'\e[35m'
GREEN=$'\e[32m' RED=$'\e[31m' CYAN=$'\e[36m'

# Green under 50%, yellow under 80%, red above.
level() {
	if [ "$1" -ge 80 ]; then printf '%s' "$RED"
	elif [ "$1" -ge 50 ]; then printf '%s' "$YELLOW"
	else printf '%s' "$GREEN"; fi
}

parts=()
add() { parts+=("$1"); }

[ -n "${model:-}" ] && add "${CYAN}${model}${RESET}${effort:+ ${DIM}·${RESET} ${effort}}"

# Directory, git branch, dirty marker, worktree, PR.
loc=""
root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)
if [ -n "$root" ]; then
	pre=$(git -C "$cwd" rev-parse --show-prefix 2>/dev/null)
	loc="${BLUE}${root##*/}${pre:+/${pre%/}}${RESET}"

	branch=$(git -C "$cwd" symbolic-ref --short -q HEAD 2>/dev/null) ||
		branch=$(git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
	if [ -n "$branch" ]; then
		dirty=""
		[ -n "$(git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null | head -c1)" ] && dirty="*"
		loc+=" ${YELLOW}(${branch}${dirty})${RESET}"
	fi

	# A linked worktree's directory name says nothing about which repo it is.
	git_dir=$(git -C "$cwd" rev-parse --path-format=absolute --git-dir 2>/dev/null)
	common=$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
	if [ -n "${wt:-}" ] || [ "$git_dir" != "$common" ]; then
		main=${common%/.git}
		loc+=" ${MAGENTA}⎇ ${main##*/}:${wt:-${root##*/}}${RESET}"
	fi

	# gh is too slow to call per render: show the cached PR number and refresh
	# it in the background every five minutes.
	if [ -n "$branch" ] && command -v gh >/dev/null 2>&1; then
		cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/claude-statusline"
		key=$(printf '%s\n%s' "$root" "$branch" | cksum | cut -d' ' -f1)
		cache="$cache_dir/pr-$key"
		if [ -z "$(find "$cache" -mmin -5 2>/dev/null)" ]; then
			mkdir -p "$cache_dir" && touch "$cache"
			(cd "$root" && gh pr view "$branch" --json number -q .number >"$cache.tmp" 2>/dev/null
				mv -f "$cache.tmp" "$cache") </dev/null >/dev/null 2>&1 &
		fi
		pr=$(cat "$cache" 2>/dev/null)
		[ -n "$pr" ] && loc+=" ${GREEN}#${pr}${RESET}"
	fi
else
	case $cwd in
		"$HOME") loc="~" ;;
		"$HOME"/*) loc="~${cwd#"$HOME"}" ;;
		*) loc=$cwd ;;
	esac
	loc="${BLUE}${loc}${RESET}"
fi
add "$loc"

[ -n "${ctx:-}" ] && add "ctx $(level "$ctx")${ctx}%${RESET}"

if [ -n "${rl5:-}" ]; then
	seg="5h $(level "$rl5")${rl5}%${RESET}"
	if [ -n "${rl5_reset:-}" ]; then
		at=$(date -r "$rl5_reset" '+%-I:%M%p' 2>/dev/null || date -d "@$rl5_reset" '+%-I:%M%p' 2>/dev/null)
		[ -n "$at" ] && seg+=" ${DIM}↻${at}${RESET}"
	fi
	add "$seg"
fi
# The weekly window only matters once it is close to running out.
[ -n "${rl7:-}" ] && [ "$rl7" -ge 70 ] && add "7d $(level "$rl7")${rl7}%${RESET}"

if [ "${added:-0}" != 0 ] || [ "${removed:-0}" != 0 ]; then
	add "${GREEN}+${added}${RESET} ${RED}−${removed}${RESET}"
fi

out=""
for p in "${parts[@]}"; do
	out+="${out:+ ${DIM}│${RESET} }$p"
done
printf '%s' "$out"
