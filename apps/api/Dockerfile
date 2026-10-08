FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN addgroup --system cocoon && adduser --system --ingroup cocoon cocoon
COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir . && chown -R cocoon:cocoon /app

USER cocoon
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test

USER root
WORKDIR /workspace/apps/api
COPY --from=runtime /app/ ./
COPY tests ./tests
COPY --from=validation_docs . /workspace/docs
RUN pip install --no-cache-dir ".[dev]" && chown -R cocoon:cocoon /workspace/apps/api

USER cocoon
CMD ["sh", "-c", "ruff check . && pytest"]
