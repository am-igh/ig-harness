# One Python image shared by the API (harness) and the worker.
FROM python:3.12-slim
# poppler-utils: `pdftotext`, used by Anne-Marie's audit checker (controle_justificatifs.py), which runs unchanged in here
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY harness/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
