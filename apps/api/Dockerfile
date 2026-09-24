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
COPY tests ./tests
RUN pip install --no-cache-dir ".[dev]"

USER cocoon
CMD ["sh", "-c", "ruff check . && pytest"]
