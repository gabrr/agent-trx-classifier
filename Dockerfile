FROM ghcr.io/astral-sh/uv:0.8.13 AS uv
FROM python:3.12-slim-bookworm AS runtime
COPY --from=uv /uv /bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_NO_CACHE=1 \
    PATH="/service/.venv/bin:$PATH" PORT=8080
WORKDIR /service
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libxcb1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 trx
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev && chown trx:trx /service
COPY alembic.ini ./
COPY migrations ./migrations
USER trx
EXPOSE 8080
CMD ["trx-api"]

# Opt-in test image; dev tooling is absent from the runtime image.
FROM runtime AS test
USER root
RUN uv sync --frozen --group dev
COPY tests ./tests
USER trx
CMD ["python", "-m", "pytest", "tests/db/test_smoke.py", "-q"]
