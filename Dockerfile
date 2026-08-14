FROM python:3.12-slim

# Copy uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency definition files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-install-project --no-dev

# Copy project source code
COPY . .

# Install project
RUN uv sync --frozen --no-dev

# Execute the application
CMD ["uv", "run", "selfbot"]
