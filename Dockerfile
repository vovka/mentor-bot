# Tests: stdlib-only code plus pytest, source mounted read-only by compose (`docker compose run --rm test`).
FROM python:3.12-slim AS test
RUN pip install --no-cache-dir pytest
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 TZ=Europe/Kyiv
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]

# Runtime image. Production runs on the host (agents need the desktop, Chrome and ~/dev); see deploy/README.md.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code @openai/codex
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
ENV DATA_DIR=/data TZ=Europe/Kyiv CODEX_HOME=/secrets/codex
CMD ["mentor", "serve"]
