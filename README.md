# visitas-api

API principal para a aplicação VisitaUp - sistema modular que permite criar e agendar visitas técnicas, registrar presença e checklist, e calcular distâncias entre endereços (para definição da logística).

CRUD de visitas, integração com ViaCEP (público, gratuito) para cálculo de distância ao serviço `distance-service`.

## Tecnologias

- Python 3.11
- FastAPI
- SQLite
- httpx
- Docker

## Endpoints principais

- `POST /visits` - cria visita
- `GET /visits` - lista visitas (params: page, size, status)
- `GET /visits/{id}` - obtém visita
- `PUT /visits/{id}` - atualiza visita
- `DELETE /visits/{id}` - remove visita
- `GET /address/cep/{cep}` - consulta ViaCEP
- `POST /visits/{id}/distance-check` - envia requisição ao distance-service
