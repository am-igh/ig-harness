# One Python image shared by the API (harness) and the worker.
FROM python:3.12-slim
WORKDIR /app
COPY harness/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
