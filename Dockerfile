FROM python:3.11

# Create a directory and copy all the files into it
RUN mkdir /app
COPY . /app
WORKDIR /app

# Install the required libraries
RUN apt-get update

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
# Expose the port
EXPOSE 8050
CMD ["gunicorn", "app:server", "-b", "0.0.0.0:8050"]