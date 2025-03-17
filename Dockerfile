FROM python:3.11-slim


# Install system dependencies required for building some Python packages
RUN apt-get update && apt-get install -y \
    gcc g++ make \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a directory and copy all the files into it
WORKDIR /app
COPY ./app /app
# Install the required libraries
RUN apt-get update

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
# Expose the port
EXPOSE 8080
CMD ["gunicorn", "--workers=3", "-b", "0.0.0.0:8080", "app:server"]