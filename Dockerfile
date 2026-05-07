FROM python:3.11-slim

RUN useradd -m -s /bin/bash botuser \
    && mkdir -p /data && chown botuser:botuser /data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

USER botuser

CMD ["python", "-m", "src.main"]
