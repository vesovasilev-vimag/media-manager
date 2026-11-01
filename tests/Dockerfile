FROM python:3.13-alpine@sha256:7984cf56ceaddebe4fefeb75d64000b9f45d8b77b11a09b24524da6cdc3af0c8
RUN apk upgrade --no-cache && apk add --no-cache ffmpeg=8.1.3-r0 postgresql17-client=17.11-r0 && ln -s /usr/bin/pg_dump /usr/local/bin/pg_dump && ln -s /usr/bin/pg_restore /usr/local/bin/pg_restore
WORKDIR /workspace
COPY backend/requirements-dev.lock /workspace/requirements-dev.lock
RUN pip install --no-cache-dir --require-hashes -r requirements-dev.lock
COPY backend /workspace/backend
COPY tests /workspace/tests
COPY deploy /workspace/deploy
ENV PYTHONPATH=/workspace/backend VIMAG_TEST_DATABASE=disposable VIMAG_TEST_DB_HOST=db VIMAG_TEST_DB_PORT=5432
CMD ["python", "-m", "pytest", "-c", "backend/pyproject.toml", "tests", "-o", "cache_dir=/tmp/pytest-cache", "--junitxml=/results/backend.xml"]
