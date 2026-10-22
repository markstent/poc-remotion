#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="${1:?Usage: scripts/bootstrap.sh <project-name>}"

# Validate project name.
if [[ ! "$PROJECT_NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "Error: use lowercase letters, numbers and hyphens."
  exit 1
fi

PACKAGE_NAME="${PROJECT_NAME//-/_}"

# Check all required files before making changes.
if [[ ! -d src/lc_poc_template ]]; then
  echo "Error: template package missing or project already bootstrapped."
  exit 1
fi

if [[ -e "src/$PACKAGE_NAME" ]]; then
  echo "Error: target Python package already exists."
  exit 1
fi

if [[ ! -f pyproject.toml || ! -f README.md ]]; then
  echo "Error: required project files are missing."
  exit 1
fi

if [[ -e .ai-project ]]; then
  echo "Error: .ai-project already exists. Refusing to overwrite it."
  exit 1
fi

if ! grep -q 'lc-poc-template' pyproject.toml; then
  echo "Error: template project metadata not found."
  exit 1
fi

# Check required tools.
for tool in uv sed; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Error: required tool '$tool' not found."
    exit 1
  fi
done

echo "Bootstrapping project: $PROJECT_NAME"

# Rename Python package.
mv src/lc_poc_template "src/$PACKAGE_NAME"

# Update project metadata.
sed -i '' "s/lc-poc-template/$PROJECT_NAME/g" pyproject.toml
sed -i '' "s/lc_poc_template/$PACKAGE_NAME/g" pyproject.toml

# Update README title.
sed -i '' "1s/.*/# $PROJECT_NAME/" README.md

# Create a local reference to the project's 1Password item.
# This is an item name, not an API key.
printf 'LITELLM_ITEM=%s-LiteLLM-dev\n' "$PROJECT_NAME" > .ai-project

# Install and verify dependencies.
uv lock
uv sync

# Run quality checks.
uv run pytest
uv run ruff check .
uv run ruff format --check .

echo ""
echo "Project initialised: $PROJECT_NAME"
echo ""
echo "Next:"
echo "1. Create a LiteLLM virtual key: ${PROJECT_NAME}-dev"
echo "2. Store it in 1Password as ${PROJECT_NAME}-LiteLLM-dev"
echo "3. Configure allowed models, MCP access and budget"
echo "4. Start OpenCode using: oc"
