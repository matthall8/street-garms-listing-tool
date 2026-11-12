FROM python:3.13.18-slim
WORKDIR /usr/local/app

# Install the application dependencies
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
ENV PATH="/usr/local/app/.venv/bin:$PATH"

# Copy in the source code
COPY app ./app
COPY labels ./labels
EXPOSE 8080

# Setup an app user so the container doesn't run as the root user
RUN useradd app
USER app

# A shell expands $PORT (Cloud Run injects it); exec keeps uvicorn as PID 1 so it receives SIGTERM.
CMD ["sh", "-c", "exec uvicorn --factory app:create_app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
