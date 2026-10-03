FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 agentzero && \
    useradd --system --uid 10001 --gid agentzero --create-home agentzero
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry==2.5.1 && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-root
COPY --chown=agentzero:agentzero app ./app
COPY --chown=agentzero:agentzero migrations ./migrations
COPY --chown=agentzero:agentzero alembic.ini ./alembic.ini
USER agentzero

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
