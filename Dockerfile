FROM python:3.10-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    gcc \
    python3-dev \
    ffmpeg \
    zip \
    curl \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip3 install --no-cache-dir -U -r requirements.txt

COPY . .

STOPSIGNAL SIGTERM

CMD ["python3", "-u", "-m", "Emilia"]