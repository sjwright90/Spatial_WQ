FROM python:3.11-slim

# Install system dependencies required for building some Python packages
RUN apt-get update && apt-get install -y \
    gcc g++ make \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first so this layer stays cached across
# app-code-only changes (pyproject.toml only exists to give pip a
# dependency list to resolve - the app itself is a flat script layout,
# not an installable package).
COPY ./app/pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir .

# Copy the rest of the app
COPY ./app /app

# Expose the port
EXPOSE 8080
CMD ["gunicorn", "--workers=3", "-b", "0.0.0.0:8080", "app:server"]