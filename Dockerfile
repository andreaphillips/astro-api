FROM python:3.11-slim

# build-essential is required by pyswisseph (Immanuel's Swiss Ephemeris
# bindings), which ships sdist-only on PyPI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn astro_api.main:app --host 0.0.0.0 --port ${PORT}"]
