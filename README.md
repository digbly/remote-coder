# remote-coder

Web API built with FastAPI.

## Setup

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Run

```bash
uvicorn app.main:app --reload
```

## Test & Lint

```bash
pytest
ruff check .
black --check .
```
