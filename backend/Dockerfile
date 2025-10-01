# backend/Dockerfile
FROM python:3.11-slim

# System deps for reportlab (freetype, jpeg, zlib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libfreetype6 \
    libfreetype6-dev \
    libjpeg62-turbo \
    libjpeg62-turbo-dev \
    zlib1g \
    zlib1g-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app.py wsgi.py gunicorn_conf.py ./
# Header image and data (optional)
COPY template.png ./        # include only if you have it
COPY funds_with_embeddings.json ./

ENV OLLAMA_URL=http://ollama:11434
ENV OLLAMA_EMBED_MODEL=nomic-embed-text
ENV OLLAMA_LLM_MODEL=gemma3:12b
ENV PORT=5000

CMD ["gunicorn", "-c", "gunicorn_conf.py", "wsgi:application"]
