# Repository Guidelines

## Project Structure & Sources of Truth

This repository installs portable macOS configuration. Root files contain shell, Vim, Git, and Homebrew settings. Application config lives under `config/`; executable tools live in `bin/`; shared shell and Python helpers live in `lib/`; agent instructions and skills live in `agents/`; and regression tests live in `tests/`.

Treat `manifest.tsv` as the source of truth for installed paths and strategies. Update it when adding an installed file. Because `.gitignore` is an allowlist, also add an explicit `!/<path>` entry for every new tracked file. Keep machine-specific values, identities, credentials, and absolute `/Users/...` paths out of the repository.

## Development and Validation

- `./install.sh --dry-run` previews installation without changing the machine.
- `./install.sh` applies the manifest idempotently and backs up conflicting targets.
- `bin/dotfiles-doctor --strict` checks installed links, dependencies, skills, runtime probes, and accidental identity leakage.
- `bash tests/install-brew-skips.sh`, `bash tests/install-agent-extras.sh`, and `bash tests/orcw.sh` run the fixture tests used in CI.
- `bash -n <script>` or `zsh -n <file>` checks shell syntax; run `shellcheck --severity=warning <script>` on changed Bash files.
- `uv run python -m py_compile lib/orcw.py` checks the Python adapter.

## Style and Naming

Write portable shell: `install.sh` must remain compatible with macOS Bash 3.2. Use tabs where the surrounding shell code does, quote expansions, and preserve `set -euo pipefail` conventions. Python uses four-space indentation, snake_case names, and the standard library unless an existing dependency is clearly better. Name executable commands with lowercase hyphenated names, such as `dotfiles-doctor`; name tests `tests/<feature>.sh`.

Keep comments focused on constraints and reasons. Do not duplicate lists or defaults already owned by `manifest.tsv`, code, or command help.

## Tests, Commits, and Pull Requests

Add the smallest fixture test that protects changed behavior; this project has no coverage target. Run the relevant test plus syntax and lint checks before submitting.

Use short, imperative commit subjects consistent with history, optionally prefixed with a type such as `fix:`. Pull requests should explain the user-visible effect or non-obvious rationale, identify risks, and list verification performed. Link related issues when applicable; include screenshots only for visible configuration changes. Never include credentials, machine-local details, or AI-generation branding.
