# Dockerfile - visitas-api
FROM python:3.11-slim

# Diretório da aplicação
WORKDIR /app

# Copia apenas o requirements primeiro (melhor cache)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código
COPY . .

# Define variáveis EXATAMENTE como no docker-compose
ENV VISITAS_DB=/data/visitas.db
ENV DISTANCE_SERVICE_URL=http://distance-service:5000

# Garante que o diretório de dados existe
RUN mkdir -p /data

# Expõe a porta do Uvicorn
EXPOSE 8000

# Comando para iniciar a API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
