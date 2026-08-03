FROM python:3.10-slim

WORKDIR /app

# Install system dependencies required for opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download rembg u2net model into cache directory so startup is fast
RUN python -c "from rembg import new_session; new_session('u2net')"

COPY app.py .

ENV PORT=5000
EXPOSE 5000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-5000}"]
