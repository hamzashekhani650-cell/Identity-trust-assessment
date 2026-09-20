FROM python:3.11-slim

WORKDIR /app

COPY trust_layer/ ./trust_layer/
COPY app.py .
COPY test_validators.py .

RUN pip install --no-cache-dir flask pytest

EXPOSE 8000

CMD ["python", "app.py"]