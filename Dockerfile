FROM python:3.11-slim

# Install system dependencies
# - imagemagick: For MoviePy text captions
# - ffmpeg: For video processing
# - libsm6, libxext6: Common OpenCV/MoviePy dependencies
RUN apt-get update && apt-get install -y \
    imagemagick \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Fix ImageMagick policy to allow Text/PDF operations (often restricted by default)
# Use find to locate policy.xml as the path varies between ImageMagick 6 and 7 (Debian defaults)
RUN find /etc -name "policy.xml" -exec sed -i 's/none/read,write/g' {} +

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories for temporary files
RUN mkdir -p static temp_storage && chmod 777 static temp_storage

# Environment variables
# PYTHONUNBUFFERED=1 ensures logs show up immediately
ENV PYTHONUNBUFFERED=1

# Render provides the PORT environment variable
# Gunicorn command to run the application
# -w 1: 1 worker (sufficient for this app, prevents race conditions on files)
# --threads 8: Handle concurrent requests
# --timeout 120: Allow long generation times
CMD gunicorn --bind 0.0.0.0:$PORT app:app --workers 1 --threads 8 --timeout 120
