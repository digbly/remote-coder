FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    API_HOST=0.0.0.0 \
    WEB_HOST=0.0.0.0 \
    VENV_DIR=/opt/venv \
    PROJECTS_ROOT=/home/remote-coder/projects \
    VSCODE_USER_DATA_ROOT=/home/remote-coder/.cache/remote-coder/vscode

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        gh \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://code-server.dev/install.sh | sh

RUN useradd --create-home --shell /bin/bash remote-coder \
    && mkdir -p \
        /app/database \
        /app/storage/logs \
        /home/remote-coder/projects \
        /home/remote-coder/.cache/remote-coder/vscode \
    && chown -R remote-coder:remote-coder /app /home/remote-coder

WORKDIR /app
COPY --chown=remote-coder:remote-coder . .

RUN python -m venv "$VENV_DIR" \
    && "$VENV_DIR/bin/pip" install --no-cache-dir . \
    && npm ci --prefix web

USER remote-coder

EXPOSE 8000 5173

CMD ["bash", "scripts/dev.sh"]
