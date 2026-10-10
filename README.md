# Remote Coder

The idea stemmed from a personal need to manage and develop my projects from anywhere. This project enables you to do that directly on the web platform—no software, no SSH, and so on.

## Setup

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

npm install --prefix web
```

## GitHub Codespaces

Create a Codespace for this repository. The dev container installs the project
dependencies, Git LFS, and `code-server` automatically. Once setup is complete,
start the API and web dev servers with:

```bash
./scripts/dev.sh
```

Open the forwarded Web port to use the app.

## Run with Docker

The production Docker image is based on Debian Bookworm. It builds the web UI
and serves it with Nginx, which also proxies API and WebSocket requests to
Uvicorn. Python 3.12, Git, Git LFS, GitHub CLI, and code-server are included.

```bash
docker build -t remote-coder .
docker run --rm --name remote-coder \
  -p 8000:8000 \
  -v remote-coder-projects:/home/remote-coder/projects \
  -v remote-coder-database:/app/database \
  -v remote-coder-logs:/app/storage/logs \
  -v remote-coder-vscode:/home/remote-coder/.cache/remote-coder/vscode \
  -e SECRET_KEY="$(openssl rand -hex 32)" \
  -e ADMIN_PASSWORD='replace-with-a-strong-password' \
  -e AI_CREDENTIAL_ENCRYPTION_KEY='replace-with-a-generated-fernet-key' \
  remote-coder
```

Generate a Fernet key with the configured project Python environment:

```bash
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Use the generated value for `AI_CREDENTIAL_ENCRYPTION_KEY` in `.env` or pass it
to the container as shown above. Keep it private and stable across restarts
and deployments. Changing it makes previously stored AI provider credentials
unreadable; those credentials must be entered again.

## AI providers and workspace chat

Sign in and open **Settings → AI providers** to add a personal OpenAI,
Anthropic, or Gemini API key. The configured bootstrap admin can also add shared
provider credentials for signed-in users. Keys are encrypted by the server and
are never returned to the browser after saving. The server must have a stable
`AI_CREDENTIAL_ENCRYPTION_KEY` configured before provider credentials can be
used.

Open a project, then choose **Chat** in the workspace tab bar. Select a
configured provider and a model returned by that provider, then start or resume
a project-scoped conversation. Chat can list and read bounded project-relative
text files, propose file changes for review, and run commands in the project
directory.

For local access, open the web app at `http://localhost:8000/`; the API docs
are at `http://localhost:8000/docs`. Because production cookies are Secure,
sign-in requires HTTPS. For production, put the container behind a
TLS-terminating reverse proxy and forward HTTPS traffic to port 8000. Keep the
generated `SECRET_KEY` stable and provide a strong `ADMIN_PASSWORD`. Named
volumes preserve projects, the SQLite database, logs, and code-server data
when the container is removed.

## Run

Run API and web dev servers together:

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

## Test & Lint

```bash
pytest
ruff check .
black --check .
```
