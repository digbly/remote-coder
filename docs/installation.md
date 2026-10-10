# Installation

This guide covers everything needed to run Remote Coder locally.

## Prerequisites

| Tool | Version | Purpose |
| --- | --- | --- |
| Python | >= 3.12 | API server |
| [uv](https://docs.astral.sh/uv/) | latest | Python environment and dependencies |
| Node.js + npm | >= 18 | Web (Vite) frontend |
| git | any | Project/worktree operations |
| [Git LFS](https://git-lfs.com/) | latest | Large files in Git repositories |
| [GitHub CLI](https://cli.github.com/) | latest | Authenticated GitHub clone and pull requests |
| [code-server](https://github.com/coder/code-server) | latest | VS Code server (IDE panel) |

Install Git LFS and initialize its Git hooks before pushing repositories that
use LFS:

```bash
sudo apt-get install git-lfs
git lfs install
```

## 1. Install code-server

The IDE panel launches a `code-server` process, and the app resolves the
`code-server` binary from `PATH` (see `vscode_binary` in `app/core/config.py`).
Without it, opening the IDE fails with:

```json
{"detail":{"code":"VSCODE_START_FAILED","message":"Không thể khởi động VS Code server"}}
```

Install it with one of the following:

```bash
# Official install script (recommended)
curl -fsSL https://code-server.dev/install.sh | sh

# npm
npm i -g code-server

# snap (classic)
sudo snap install code-server --classic
```

Verify the install:

```bash
code-server --version
```

If the binary lives outside `PATH`, point the app at it via `.env`:

```
VSCODE_BINARY=/absolute/path/to/code-server
```

## 2. Set up the API

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## 3. Set up the web frontend

```bash
npm install --prefix web
```

## 4. Configure environment

```bash
cp .env.example .env
```

Generate a Fernet key with the project's Python environment:

```bash
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Copy the generated value into `.env` as `AI_CREDENTIAL_ENCRYPTION_KEY`. Keep
this key secret, back it up securely, and reuse the same value across restarts
and deployments. Do not generate a new key when restarting the app: changing
it makes saved AI provider credentials unreadable, so they must be entered
again.

Then adjust the other values in `.env` as needed (admin credentials, etc.).

Authenticate the GitHub CLI as the same operating-system user that runs the API.
GitHub project cloning uses that login, including for private repositories:

```bash
gh auth login
gh auth status
```

The Dev Container installs GitHub CLI automatically. For other environments,
install it using the [official installation instructions](https://github.com/cli/cli/blob/trunk/docs/install_linux.md),
then verify it with `gh --version`.

## 5. Run

Run the API and web dev servers together:

```bash
./scripts/dev.sh
```

- API: http://127.0.0.1:8000 (docs at `/docs`)
- Web (Vite): http://localhost:5173

Or run each separately:

```bash
uvicorn app.main:app --reload
npm run dev --prefix web
```

## Troubleshooting

### `VSCODE_START_FAILED`

The VS Code server could not start. Most commonly `code-server` is missing
from `PATH`. Confirm with `code-server --version` and install it (step 1).

Other things to check:

- Ports `8800-8900` (or `VSCODE_PORT_START`/`VSCODE_PORT_END`) are free.
- `code-server` has write access to its data dir
  (`~/.cache/remote-coder/vscode` by default).

### `uvicorn not found`

The API dependencies are not installed. Run step 2.

### `web/node_modules not found`

The frontend dependencies are not installed. Run step 3.
