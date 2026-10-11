# Installation

This guide explains how to install and run Remote Coder locally.

## Requirements

- Python 3.12 or later and [uv](https://docs.astral.sh/uv/)
- Node.js 18 or later and npm
- Git

Install these tools if you need the corresponding integrations:

- [code-server](https://github.com/coder/code-server) for the VS Code panel.
- [agent-browser](https://github.com/vercel-labs/agent-browser) and Chrome for
  the Browser tab.
- [GitHub CLI](https://cli.github.com/) to clone private GitHub repositories
  or create pull requests.

## Install dependencies

Set up the API environment:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Install the web dependencies:

```bash
npm install --prefix web
```

## Configure the application

Create the local environment file:

```bash
cp .env.example .env
```

Set `ADMIN_PASSWORD` in `.env` before exposing the app beyond your local
machine. To save AI provider credentials, set `AI_CREDENTIAL_ENCRYPTION_KEY`
to a Fernet key. Generate one with the project environment:

```bash
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Keep this key secret and reuse it across restarts. Changing it makes saved AI
provider credentials unreadable.

If you use GitHub integrations, authenticate the GitHub CLI as the same
operating-system user that runs the API:

```bash
gh auth login
```

## Run the application

Start the API and web development servers:

```bash
./scripts/dev.sh
```

The script creates `.env` from `.env.example` if it does not exist.

- Web app: http://localhost:5173
- API: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

For help resolving setup and runtime errors, see
[Troubleshooting](troubleshooting.md).
