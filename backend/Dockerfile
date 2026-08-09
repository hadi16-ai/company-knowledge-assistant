FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2, PDF/embedding libraries, and OCR (tesseract-ocr
# pulls in tesseract-ocr-eng on Debian, so English recognition works out of the box).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# torch is a transitive dep of sentence-transformers; install the CPU-only build
# first so pip doesn't pull the ~4.5GB CUDA/nvidia-* wheels (this app is CPU-only).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
