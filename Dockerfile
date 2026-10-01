FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       antiword \
       poppler-utils \
       tesseract-ocr \
       tesseract-ocr-ara \
       tesseract-ocr-heb \
       tesseract-ocr-spa \
       tesseract-ocr-fra \
       tesseract-ocr-deu \
       fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && pip install torch==2.14.1+cpu --index-url https://download.pytorch.org/whl/cpu

COPY scripts/prepare_detector.py ./scripts/prepare_detector.py
RUN python scripts/prepare_detector.py /opt/txtzi/detector
COPY THIRD_PARTY_NOTICES.md /opt/txtzi/detector/THIRD_PARTY_NOTICES.md
ENV DETECTOR_PROVIDER=local \
    DETECTOR_MODEL_DIR=/opt/txtzi/detector \
    HF_HUB_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false

COPY app ./app
COPY static ./static

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
