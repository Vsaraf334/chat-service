FROM python:3.12-slim

# uv, copied from its official image (pinned to the version used in development)
COPY --from=ghcr.io/astral-sh/uv:0.11.12 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first, in their own layer, so code changes don't reinstall them
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Then the application code
COPY app ./app

EXPOSE 8000

# Run as a non-root user
RUN useradd --create-home appuser
USER appuser

CMD ["uv", "run", "--no-sync", "fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
