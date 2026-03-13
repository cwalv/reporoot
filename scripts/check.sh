#!/bin/sh
# Shared lint / format / typecheck checks.
# Used by .githooks/pre-commit and .github/workflows/publish.yml.

set -e

uv run ruff check
uv run ruff format --check
uv run pyright
