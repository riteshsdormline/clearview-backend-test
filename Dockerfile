# OpenCV needs a couple of system libs not present in the slim Python image.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MODEL_DIR=models
ENV PORT=7860
ENV ALLOWED_ORIGINS=*
ENV MAX_UPLOAD_BYTES=10485760

EXPOSE 7860

# --workers 1 by default: this pipeline loads two DNN models per request
# process and does CPU-bound OpenCV work, so scale via more container
# instances (or a process manager) rather than many uvicorn workers sharing
# one CPU allocation, unless you've sized the container generously.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
