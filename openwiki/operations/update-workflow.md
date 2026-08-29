# OpenWiki update workflow

## Trigger and permissions

`.github/workflows/openwiki-update.yml` defines the `OpenWiki Update` workflow. It runs on:

- a daily schedule: `0 8 * * *` (08:00 UTC), and
- `workflow_dispatch` for manual execution.

The job requests `contents: write` and `pull-requests: write`, which support generating the documentation changes and opening the resulting pull request.

## Execution

The job runs on Ubuntu with Node.js 22. Its steps are:

1. Check out the repository with `actions/checkout@v4`.
2. Install OpenWiki globally using `npm install --global openwiki`.
3. Run `openwiki code --update --print`.
4. Use `peter-evans/create-pull-request` to create or refresh branch `openwiki/update`.

The pull request includes `openwiki`, `AGENTS.md`, `CLAUDE.md`, and the workflow file. Its commit message and title are `docs: update OpenWiki`.

## Configuration

The workflow passes provider and observability configuration through environment variables. Secret values are stored in GitHub Actions secrets and are not documented here. The non-secret names and selected values are:

- `OPENWIKI_PROVIDER`: `openrouter`
- `OPENROUTER_API_KEY`: GitHub secret reference used by the provider
- `OPENWIKI_MODEL_ID`: `z-ai/glm-5.2`
- `LANGSMITH_API_KEY`: GitHub secret reference for tracing
- `LANGCHAIN_PROJECT`: `openwiki`
- `LANGCHAIN_TRACING_V2`: `true`

Do not paste or commit the secret values. Changes to provider, model, permissions, or pull-request paths should be reviewed together because they affect both generation and delivery.

## Change guidance

When modifying this workflow, validate YAML structure and check that the generated paths remain included in `add-paths`. If the repository gains application build or test steps, document those separately rather than assuming the OpenWiki job validates application behavior: the current workflow has no application test or build command.
