# Build from the repository root: docker build -f backend/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# No compiler toolchain needed: every pinned dependency in requirements.txt
# ships manylinux wheels (verified with `pip download --only-binary=:all:`),
# which also avoids apt entirely (flaky/unavailable in some build sandboxes).
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY backend/workers ./workers
COPY scripts ./scripts

RUN mkdir -p /srv/data /srv/artifacts

ENV NOESIS_ARTIFACT_ROOT=/srv/artifacts \
    NOESIS_DATABASE_URL=sqlite:////srv/data/noesis.db

EXPOSE 8000
CMD ["sh", "-c", "mkdir -p \"$NOESIS_ARTIFACT_ROOT\" && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
