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
