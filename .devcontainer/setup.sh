#!/usr/bin/env bash
set -euo pipefail

uv sync --group dev --python /usr/local/bin/python
for scope in --global --local; do
	if git config "$scope" --get-all core.hooksPath >/dev/null; then
		git config "$scope" --unset-all core.hooksPath
	fi
done
uv run pre-commit install --install-hooks --hook-type pre-commit