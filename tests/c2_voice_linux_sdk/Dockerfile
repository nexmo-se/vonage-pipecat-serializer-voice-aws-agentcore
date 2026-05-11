FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy test script
COPY test_voice_linux_sdk.py .

CMD ["python", "test_voice_linux_sdk.py"]
