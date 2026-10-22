# poc-remotion

Reusable Python and AI proof-of-concept template for building professional, reproducible projects.

## Technology

- Python 3.13 and uv
- pytest and Ruff
- OpenCode
- LiteLLM gateway
- 1Password credential management
- Shared MCP servers and agent skills

## Getting Started

### 1. Create a new project

Create an independent GitHub repository using the `markstent/lc-poc-template` template.

Clone the new repository into:

    ~/Documents/Projects/<project-name>

Run the bootstrap script once:

    ./scripts/bootstrap.sh <project-name>

The bootstrap configures the Python package, project metadata, dependencies and local project identity.

Do not run bootstrap again on an existing project.

### 2. Configure LiteLLM

In the LiteLLM dashboard:

    http://localhost:4000/ui

Create a project-specific virtual key.

Recommended alias:

    <project-name>-dev

Configure:
- Allowed model aliases
- MCP access group, normally `lab-default`
- Appropriate project budget

LiteLLM virtual keys control project access and spending.

Upstream provider credentials are configured separately in LiteLLM using reusable named credentials. Do not embed API keys in model deployments.

### 3. Configure 1Password

Store the project virtual key in a 1Password API Credential item.

Recommended item name:

    <project-name>-LiteLLM-dev

Store the key in the `credential` field.

The local `.ai-project` file contains only the item reference:

    LITELLM_ITEM=<project-name>-LiteLLM-dev

Never store the actual API key in `.ai-project` or Git.

### 4. Configure OpenCode

The global OpenCode configuration is:

    ~/.config/opencode/opencode.jsonc

It contains shared LiteLLM provider settings, model aliases and the MCP gateway connection.

Project-level `opencode.jsonc` may specify a default model:

    {
      "$schema": "https://opencode.ai/config.json",
      "model": "litellm/<public-model-alias>"
    }

The public model alias must match the corresponding LiteLLM deployment.

The global model catalogue determines which models OpenCode can select. The project virtual key determines which models LiteLLM permits.

### 5. Start OpenCode

From the project directory:

    oc

The `oc` launcher:
1. Reads the project's `.ai-project`.
2. Retrieves the corresponding virtual key from 1Password.
3. Supplies it as `LITELLM_API_KEY`.
4. Starts OpenCode.

Inside OpenCode:
- `/models` selects a model.
- `/mcp` checks the shared LiteLLM MCP connection.

A single LiteLLM MCP connection can expose multiple authorised downstream tools.

## Development

Install dependencies:

    uv sync

Run tests:

    uv run pytest

Run linting:

    uv run ruff check .

Check formatting:

    uv run ruff format --check .

Start the coding agent:

    oc

## Project Structure

- `src/` - application code
- `tests/` - automated tests
- `docs/` - specifications and decisions
- `experiments/` - exploratory work
- `data/` - local datasets
- `scripts/` - project utilities
- `AGENTS.md` - coding agent instructions
- `.ai-project` - local 1Password item reference, ignored by Git
- `opencode.jsonc` - optional project-specific OpenCode settings

## Security

- Never commit secrets, API keys or sensitive data.
- Store credentials in 1Password.
- Use project-specific LiteLLM virtual keys.
- Keep upstream provider credentials inside LiteLLM.
- Respect model permissions, MCP access groups and budgets.
- Review changes before committing or pushing.

For complete procedures, refer to the Latent Space Experimentation Lab AI Project Setup Instructions.
