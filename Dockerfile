FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code @openai/codex

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENV DATA_DIR=/data TZ=Europe/Kyiv CODEX_HOME=/secrets/codex

CMD ["mentor", "serve", "--with-scheduler"]
