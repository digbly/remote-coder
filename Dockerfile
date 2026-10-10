FROM node:22-bookworm-slim AS web-build

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    DEBUG=false \
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
        nginx \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://code-server.dev/install.sh | sh

RUN useradd --create-home --shell /bin/bash remote-coder \
    && mkdir -p \
        /app/database \
        /app/storage/logs \
        /home/remote-coder/projects \
        /home/remote-coder/.cache/remote-coder/vscode \
        /tmp/nginx/client_body \
        /tmp/nginx/proxy \
        /tmp/nginx/fastcgi \
        /tmp/nginx/uwsgi \
        /tmp/nginx/scgi \
    && chown -R remote-coder:remote-coder \
        /app \
        /home/remote-coder \
        /tmp/nginx

WORKDIR /app
COPY --chown=remote-coder:remote-coder pyproject.toml README.md ./
COPY --chown=remote-coder:remote-coder app ./app
COPY --from=web-build --chown=remote-coder:remote-coder /web/dist ./web/dist
COPY nginx.conf /etc/nginx/nginx.conf
COPY scripts/entrypoint.sh /usr/local/bin/remote-coder-entrypoint

RUN python -m venv "$VENV_DIR" \
    && "$VENV_DIR/bin/pip" install --no-cache-dir . \
    && chmod 755 /usr/local/bin/remote-coder-entrypoint

USER remote-coder

EXPOSE 8000
STOPSIGNAL SIGTERM

CMD ["/usr/local/bin/remote-coder-entrypoint"]
