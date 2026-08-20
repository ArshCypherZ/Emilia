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
    gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y nodejs \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/sessions && useradd -m emilia && chown -R emilia /app
USER emilia

STOPSIGNAL SIGTERM

HEALTHCHECK CMD python3 -c "import os,sys,time; p='/tmp/emilia_heartbeat'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<600 else 1)"

CMD ["python3", "-u", "-m", "Emilia"]
