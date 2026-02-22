FROM astral/uv:python3.14-trixie-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked


FROM python:3.14-slim-trixie

RUN groupadd -r selfbot && useradd -r -g selfbot selfbot

WORKDIR /app
COPY --from=builder --chown=selfbot:selfbot /app /app

USER selfbot

ENV PATH="/app/.venv/bin:$PATH"
CMD ["selfbot"]
