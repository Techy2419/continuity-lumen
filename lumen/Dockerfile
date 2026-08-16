# Lumen mock backend -- container for Google Cloud Run

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run sets $PORT automatically; gunicorn binds to it here.
# --threads matters because Lumen runs a background simulator thread
# alongside request handling.
CMD exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 app:app
