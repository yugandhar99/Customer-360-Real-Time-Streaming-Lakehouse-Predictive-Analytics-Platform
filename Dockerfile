FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000 \
    EXECUTION_MODE=local \
    LOCAL_BACKEND=sqlite \
    AWS_ENABLED=false \
    FLASK_DEBUG=false \
    LOG_TO_FILE=true

WORKDIR /app

RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY config.py .
COPY ingestion ./ingestion
COPY storage ./storage
COPY transformations ./transformations
COPY processing ./processing
COPY ml ./ml
COPY dashboard ./dashboard
COPY utils ./utils
COPY aws_sql ./aws_sql
COPY dags ./dags
COPY dbt_models ./dbt_models
COPY gcp_sql_models ./gcp_sql_models

RUN mkdir -p /app/logs /app/storage \
    && chown -R app:app /app

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','5000') + '/health')" || exit 1

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${GUNICORN_WORKERS:-1} --timeout 60 --access-logfile - --error-logfile - dashboard.app:app"]
