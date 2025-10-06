# syntax=docker/dockerfile:1.6

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy controller requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy controller app
COPY app /app/app
COPY ui /app/ui
COPY config /app/config

# Create data dir
RUN mkdir -p /app/data

EXPOSE 8080

ENV HOST=0.0.0.0 \
    PORT=8080 \
    DATABASE_PATH=/app/data/deploybot.db

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
