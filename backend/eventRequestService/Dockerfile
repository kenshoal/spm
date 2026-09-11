FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EVENT_REQUEST_DB_PATH=/data/db.sqlite3

WORKDIR /service

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir /data \
    && chown app:app /data

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

USER app

EXPOSE 8000
VOLUME ["/data"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

