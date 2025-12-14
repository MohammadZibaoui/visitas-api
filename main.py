# main.py
from fastapi import FastAPI, HTTPException, status, Path
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import sqlite3
import httpx
import os
from fastapi.middleware.cors import CORSMiddleware

# Configurações

DB = os.getenv("VISITAS_DB", "visitas.db")
DISTANCE_SERVICE_URL = os.getenv("DISTANCE_SERVICE_URL", "http://distance-service:5000")

app = FastAPI(
    title="visitas-api - VisitaUp",
    version="1.1.0",
    description="""
API principal do sistema **VisitaUp**.

Gerencia visitas técnicas, consulta CEP pelo serviço externo **ViaCEP**
e integra-se ao microsserviço **distance-service** para cálculo de distâncias.

Componentes:
- **visitas-api** → API de visitas (este serviço)
- **distance-service** → cálculo de distância
- **ViaCEP** → serviço de endereços externo
""",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ou apenas ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Tags do Swagger
tags_metadata = [
    {"name": "Visitas", "description": "CRUD completo de visitas técnicas."},
    {"name": "Endereços", "description": "Consulta de CEP via ViaCEP."},
    {"name": "Distância", "description": "Cálculo de distância usando o microserviço distance-service."},
    {"name": "Sistema", "description": "Rotas internas de health e diagnóstico."},
]

app.openapi_tags = tags_metadata


# Banco de Dados

def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row      # retorna dict-like
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS visits (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      date TEXT,
      cep TEXT,
      address TEXT,
      city TEXT,
      uf TEXT,
      lat REAL,
      lon REAL,
      responsible TEXT,
      status TEXT,
      created_at TEXT,
      updated_at TEXT
    )""")
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup():
    init_db()


# Modelos Pydantic

class Location(BaseModel):
    lat: float = Field(..., example=-19.9232)
    lon: float = Field(..., example=-43.9419)


class VisitIn(BaseModel):
    title: str = Field(..., example="Visita Técnica - Mina X")
    description: Optional[str] = Field(None, example="Inspeção de rotina")
    date: Optional[str] = Field(None, example="2025-01-10T14:00:00")
    cep: Optional[str] = Field(None, example="30140071")
    address: Optional[str] = Field(None, example="Av. Afonso Pena, 1500")
    lat: Optional[float] = Field(None, example=-19.9232)
    lon: Optional[float] = Field(None, example=-43.9419)
    responsible: Optional[str] = Field(None, example="Carlos Alberto")
    status: Optional[str] = Field(None, example="scheduled")


class VisitOut(VisitIn):
    id: int
    created_at: Optional[str]
    updated_at: Optional[str]


class DistanceCheckRequest(BaseModel):
    origin: Location
    destination: Location


# Rotas de VISITAS

@app.post(
    "/visits",
    status_code=status.HTTP_201_CREATED,
    tags=["Visitas"],
    response_model=dict,
    summary="Registrar uma nova visita",
    description="Cria uma nova visita no banco e retorna o ID gerado."
)
async def create_visit(payload: VisitIn):
    now = datetime.utcnow().isoformat()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
      INSERT INTO visits (title, description, date, cep, address, city, uf,
                          lat, lon, responsible, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.title, payload.description, payload.date, payload.cep,
        payload.address, None, None, payload.lat, payload.lon,
        payload.responsible, payload.status or "scheduled", now, now
    ))

    conn.commit()
    vid = cur.lastrowid
    conn.close()

    return {"id": vid}


@app.get(
    "/visits",
    tags=["Visitas"],
    response_model=List[VisitOut],
    summary="Listar visitas",
    description="Lista todas as visitas cadastradas com paginação."
)
async def list_visits(
    page: int = 1,
    size: int = 50,
    status: Optional[str] = None
):
    page = max(page, 1)
    size = min(max(size, 1), 100)
    offset = (page - 1) * size

    conn = get_conn()
    cur = conn.cursor()

    base_query = """
        SELECT * FROM visits
        {where}
        ORDER BY COALESCE(date, created_at) DESC
        LIMIT ? OFFSET ?
    """

    if status:
        query = base_query.format(where="WHERE status = ?")
        cur.execute(query, (status, size, offset))
    else:
        query = base_query.format(where="")
        cur.execute(query, (size, offset))

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


@app.get(
    "/visits/{visit_id}",
    tags=["Visitas"],
    response_model=VisitOut,
    summary="Buscar visita por ID",
    description="Retorna todos os dados de uma visita específica."
)
async def get_visit(visit_id: int = Path(..., gt=0)):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM visits WHERE id = ?", (visit_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Visit not found")

    return dict(row)


@app.put(
    "/visits/{visit_id}",
    tags=["Visitas"],
    response_model=dict,
    summary="Atualizar visita",
    description="Atualiza todos os campos de uma visita existente."
)
async def update_visit(visit_id: int, payload: VisitIn):

    now = datetime.utcnow().isoformat()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
      UPDATE visits SET
        title=?, description=?, date=?, cep=?, address=?, lat=?, lon=?,
        responsible=?, status=?, updated_at=?
      WHERE id=?
    """, (
        payload.title, payload.description, payload.date, payload.cep,
        payload.address, payload.lat, payload.lon, payload.responsible,
        payload.status or "scheduled", now, visit_id
    ))

    conn.commit()
    conn.close()

    return {"updated": visit_id}


@app.delete(
    "/visits/{visit_id}",
    tags=["Visitas"],
    response_model=dict,
    summary="Excluir visita",
    description="Remove uma visita definitivamente do banco."
)
async def delete_visit(visit_id: int):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM visits WHERE id = ?", (visit_id,))
    conn.commit()
    conn.close()

    return {"deleted": visit_id}


# Integração com ViaCEP

@app.get(
    "/address/cep/{cep}",
    tags=["Endereços"],
    summary="Consultar endereço pelo CEP",
    description="Consulta o serviço ViaCEP e retorna endereço padronizado."
)
async def via_cep(cep: str):

    cep_clean = "".join(filter(str.isdigit, cep))
    url = f"https://viacep.com.br/ws/{cep_clean}/json/"

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=10)
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao acessar ViaCEP")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="ViaCEP retornou erro")

    data = r.json()
    if data.get("erro"):
        raise HTTPException(status_code=404, detail="CEP não encontrado")

    return data


# Integração com distance-service

@app.post(
    "/visits/{visit_id}/distance-check",
    tags=["Distância"],
    summary="Calcular distância entre dois pontos",
    description="Consulta o microserviço distance-service e retorna a distância em km."
)
async def distance_check(visit_id: int, payload: DistanceCheckRequest):

    url = f"{DISTANCE_SERVICE_URL}/distance"

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                json={
                    "from": payload.origin.dict(),
                    "to": payload.destination.dict()
                },
                timeout=10
            )
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao contatar distance-service")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="distance-service retornou erro")

    return r.json()


# Rotas do Sistema

@app.get(
    "/health",
    tags=["Sistema"],
    summary="Status do serviço",
    description="Retorna o status básico da API."
)
async def health():
    return {"status": "ok", "service": "visitas-api"}
