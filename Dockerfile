FROM python:3.11-slim

# Node.js (for Claude CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash botuser \
    && mkdir -p /data && chown botuser:botuser /data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY .claude/ .claude/
COPY src/ src/
COPY entrypoint.sh /entrypoint.sh

USER botuser

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "src.main"]
