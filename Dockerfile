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

ENV MODEL_DIR=/app
ENV PORT=7860
ENV ALLOWED_ORIGINS=*
ENV MAX_UPLOAD_BYTES=10485760

EXPOSE 7860

# --workers 1 is mandatory for 512MB RAM to prevent loading multiple
# instances of the AI model.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
