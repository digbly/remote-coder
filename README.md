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
dependencies and `code-server` automatically. Once setup is complete, start the
API and web dev servers with:

```bash
./scripts/dev.sh
```

Open the forwarded Web port to use the app.

## Run with Docker

The Docker image is based on Debian Bookworm and includes Python 3.12, Node.js
22, Git, GitHub CLI, and code-server.

```bash
docker build -t remote-coder .
docker run --rm --name remote-coder \
  -p 8000:8000 -p 5173:5173 \
  -v remote-coder-projects:/home/remote-coder/projects \
  -v remote-coder-database:/app/database \
  -v remote-coder-logs:/app/storage/logs \
  -e ADMIN_PASSWORD=change-this-password \
  remote-coder
```

Open http://localhost:5173 for the web app or http://localhost:8000/docs for
the API. The named volumes preserve projects, the SQLite database, and logs
when the container is removed. This configuration runs the development
servers; configure a unique `SECRET_KEY` and production deployment settings
before exposing the app publicly.

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
