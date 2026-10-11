# Troubleshooting

If you have not installed or configured the application yet, see the
[installation guide](installation.md).

## `VSCODE_START_FAILED`

The VS Code server could not start. Confirm that `code-server` is installed
and available on `PATH`:

```bash
code-server --version
```

If the binary is outside `PATH`, set `VSCODE_BINARY` in `.env` to its absolute
path. Also check that:

- Ports `8800-8900` (or the range configured by `VSCODE_PORT_START` and
  `VSCODE_PORT_END`) are available.
- The API user can write to the code-server data directory, which defaults to
  `~/.remote-coder/vscode/cache`.

## `BROWSER_START_FAILED` or a blank Browser tab

The Browser tab needs `agent-browser` and Chrome for Testing. Install both as
the same operating-system user that runs the API:

```bash
npm install -g agent-browser
agent-browser install --with-deps
```

On Linux, `--with-deps` also installs required system libraries and may need
`sudo`. If the executable is outside `PATH`, set `BROWSER_BINARY` in `.env`.
Verify the CLI and its stream server:

```bash
agent-browser --version
agent-browser stream status --json
```

Restart the API after installing `agent-browser`. If the tab still cannot
connect, check the API log for a `browser stream connect failed` message and
confirm the reported port is reachable. To turn off the Browser tab, set
`BROWSER_ENABLED=false` in `.env`.

The Browser tab and AI agent share one browser session per project. To restrict
which hosts it can visit, set `BROWSER_ALLOWED_DOMAINS` to a comma-separated
list of allowed domains.

## `uvicorn not found`

The API dependencies are missing. From the repository root, activate the
project environment and install them:

```bash
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## `web/node_modules not found`

The web dependencies are missing. From the repository root, run:

```bash
npm install --prefix web
```
