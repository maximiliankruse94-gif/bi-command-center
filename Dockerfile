FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    BICC_ENV=prod BICC_SOURCE_MODE=google TZ=Europe/Berlin
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY bi ./bi
COPY ui ./ui
COPY config ./config
COPY docs ./docs
COPY .streamlit ./.streamlit
COPY app.py .
RUN useradd -m appuser && mkdir -p /app/data && chown -R appuser /app
USER appuser
EXPOSE 8080
# Webanwendung (Cloud Run Service). Der Sync-Job nutzt dasselbe Image mit: python -m bi.sync --trigger scheduled
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8080} --server.address=0.0.0.0"]
