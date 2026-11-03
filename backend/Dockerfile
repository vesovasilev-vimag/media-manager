FROM python:3.13-alpine@sha256:7984cf56ceaddebe4fefeb75d64000b9f45d8b77b11a09b24524da6cdc3af0c8
RUN apk upgrade --no-cache && apk add --no-cache ffmpeg=8.1.3-r0 postgresql17-client=17.11-r0 && ln -s /usr/bin/pg_dump /usr/local/bin/pg_dump && ln -s /usr/bin/pg_restore /usr/local/bin/pg_restore
WORKDIR /app
COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
RUN python -m pip uninstall -y pip setuptools && rm -rf /usr/local/lib/python3.13/ensurepip
RUN addgroup -g 1000 vimag && adduser -D -u 1000 -G vimag vimag
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
USER 1000:1000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "app.api"]
