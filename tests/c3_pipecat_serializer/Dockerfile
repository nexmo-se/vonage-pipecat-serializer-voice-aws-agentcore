FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libssl-dev \
    libexpat1 \
    libpulse0 \
    alsa-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

COPY serializer_echo_bot.py .

CMD ["python", "serializer_echo_bot.py"]
