#!/usr/bin/env bash

# Shared by the installer's download step and the doctor's checks.
# shellcheck disable=SC2034
VENDORED_SKILLS="github/gh-stack@gh-stack vercel-labs/skills@find-skills"

COMPONENT_CATALOG="$DOTFILES/components.tsv"
COMPONENT_SELECTION_FILE="${DOTFILES_COMPONENTS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/dotfiles/components}"

component_field() {
	awk -F '\t' -v name="$1" -v field="$2" '$1 == name {print $field; found=1; exit} END {if (!found) exit 1}' "$COMPONENT_CATALOG"
}

component_enabled() {
	case " ${COMPONENT_SELECTED:-core} " in *" $1 "*) return 0 ;; esac
	return 1
}

components_read() {
	local name
	COMPONENT_SAVED=core
	[ -f "$COMPONENT_SELECTION_FILE" ] || return 0
	while IFS= read -r name || [ -n "$name" ]; do
		case "$name" in ''|'#'*) continue ;; esac
		component_field "$name" 1 >/dev/null || {
			printf 'dotfiles: unknown saved component "%s"; use install.sh select to replace the selection.\n' "$name" >&2
			return 1
		}
		COMPONENT_SAVED="$COMPONENT_SAVED $name"
	done <"$COMPONENT_SELECTION_FILE"
}

_component_resolve() {
	local name=$1 stack=${2:-} dependencies dependency
	case " $COMPONENT_RESOLVED " in *" $name "*) return 0 ;; esac
	case " $stack " in
		*" $name "*) printf 'dotfiles: component dependency cycle at %s\n' "$name" >&2; return 1 ;;
	esac
	dependencies=$(component_field "$name" 3) || {
		printf 'dotfiles: unknown component "%s" (see install.sh list).\n' "$name" >&2
		return 1
	}
	for dependency in $dependencies; do
		[ "$dependency" = - ] || _component_resolve "$dependency" "$stack $name" || return 1
	done
	COMPONENT_RESOLVED="${COMPONENT_RESOLVED:+$COMPONENT_RESOLVED }$name"
}

components_resolve() {
	local name
	COMPONENT_RESOLVED=
	for name in core $1; do _component_resolve "$name" || return 1; done
}

components_packages() {
	local component formula cask
	for component in $1; do
		for formula in $(component_field "$component" 4); do
			[ "$formula" = - ] || printf 'brew\t%s\n' "$formula"
		done
		for cask in $(component_field "$component" 5); do
			[ "$cask" = - ] || printf 'cask\t%s\n' "$cask"
		done
	done | sort -u
}

components_save() {
	local name temporary
	mkdir -p "$(dirname "$COMPONENT_SELECTION_FILE")"
	temporary=$(mktemp "${COMPONENT_SELECTION_FILE}.XXXXXX") || return 1
	for name in $COMPONENT_SELECTED; do printf '%s\n' "$name"; done >"$temporary"
	chmod 600 "$temporary"
	mv "$temporary" "$COMPONENT_SELECTION_FILE"
}
