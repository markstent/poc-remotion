# POC Agent Instructions

## Principles
- Build professional, reproducible proof-of-concepts.
- Prefer simple, modular, maintainable code.
- Avoid over-engineering and unnecessary dependencies.
- Make the smallest correct change.
- Do not modify unrelated code.
- Be concise. Never use em dashes.

## Development
- Python 3.13 with uv.
- pytest for tests.
- Ruff for linting and formatting.
- Use type hints for public interfaces.
- Keep experiments separate from production code.
- Document significant technical decisions.

## Workflow
1. Read README.md and relevant documentation.
2. Inspect existing code before modifying it.
3. Propose a plan for substantial changes.
4. Implement in small, testable increments.
5. Run tests and lint checks.
6. Review git diff before committing.
7. Summarise changes, results and outstanding issues.

## Quality
- Write tests for important logic and edge cases.
- Prefer deterministic and reproducible results.
- Do not silently swallow exceptions.
- Avoid unnecessary abstractions.
- Use configuration rather than hard-coded values.

## AI and Models
- Route approved model calls through LiteLLM.
- Use the configured LiteLLM provider and model aliases.
- Keep development and runtime model selection separate.
- Reuse globally configured MCP servers through LiteLLM.
- Respect project virtual-key permissions and budgets.
- Do not duplicate shared OpenCode configuration.
- Do not bypass LiteLLM routing without explicit approval.

## Credentials and Security
- Never commit, print, log or expose secrets or API keys.
- Use 1Password for credential storage.
- Never access unrelated 1Password items or vaults.
- Never retrieve upstream provider credentials unnecessarily.
- Use the project-specific LiteLLM virtual key.
- The local .ai-project identifies the project's 1Password item.
- Do not put API keys in .ai-project or opencode.jsonc.
- Do not embed upstream API keys in model deployments.
- Never commit sensitive datasets.
- Use synthetic data unless explicitly authorised.

## Human Approval
Ask before:
- Major architecture changes.
- Introducing significant dependencies.
- Destructive Git or filesystem operations.
- Modifying authentication or credentials.
- Changing shared workstation configuration.
- Deployment or infrastructure changes.
- Using paid external services outside approved budgets.
- Committing or pushing changes unless explicitly authorised.
