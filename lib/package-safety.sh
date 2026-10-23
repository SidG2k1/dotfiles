#!/usr/bin/env bash

package_script_approvals_supported() {
	local version
	if command -v npm >/dev/null 2>&1 && ! npm install-scripts --help >/dev/null 2>&1; then
		printf 'Update npm to a version supporting install-script approvals.\n' >&2
		return 1
	fi
	if command -v pnpm >/dev/null 2>&1; then
		version=$(pnpm --version) || return 1
		if [ "${version%%.*}" -lt 10 ]; then
			printf 'Update pnpm to version 10 or newer for dependency build approvals.\n' >&2
			return 1
		fi
	fi
}

# pnpm 10 stores settings in INI; newer versions use YAML. Let its CLI
# preserve registry credentials and choose the correct file on each machine.
pnpm_security_config() {
	local action=$1 version key value config_key actual policy
	command -v pnpm >/dev/null 2>&1 || return 0
	version=$(pnpm --version) || return 1
	policy=$(jq -er 'to_entries[] | [.key, (.value | tojson)] | @tsv' \
		"$DOTFILES/config/package-safety/pnpm.json") || return 1
	while IFS=$'\t' read -r key value; do
		config_key=$key
		if [ "${version%%.*}" -lt 11 ]; then
			config_key=$(printf '%s' "$key" | sed -E 's/([a-z])([A-Z])/\1-\2/g' | tr '[:upper:]' '[:lower:]')
		fi
		actual=$(pnpm --dir "$HOME" config get "$config_key" --json) || return 1
		if printf '%s' "$actual" | jq -e --argjson expected "$value" \
			'. == $expected or tostring == ($expected | tostring)' >/dev/null 2>&1; then
			continue
		fi
		if [ "$action" = check ]; then
			printf 'pnpm: %s does not match the package-safety policy\n' "$key" >&2
			return 1
		fi
		if [ "${version%%.*}" -lt 11 ]; then
			value=$(printf '%s' "$value" | jq -r .) || return 1
			pnpm config set --global "$config_key" "$value" || return 1
		else
			pnpm config set --global --json "$config_key" "$value" || return 1
		fi
	done <<< "$policy"
}
