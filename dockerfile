# Dockerfile - visitas-api
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV VISITAS_DB=/app/visitas.db
ENV DISTANCE_SERVICE_URL=http://distance-service:5000

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]