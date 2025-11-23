# main.py
import sqlite3
import httpx
import os
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, status, Path
from pydantic import BaseModel, Field

# Configurações
DB = os.getenv("VISITAS_DB", "visitas.db")
DISTANCE_SERVICE_URL = os.getenv("DISTANCE_SERVICE_URL", "http://distance-service:5000")

app = FastAPI(
    title="visitas-api - VisitaUp",
    version="1.0.0",
    description="""
API principal do sistema **VisitaUp**.

Esta API gerencia visitas técnicas, integra-se com o serviço externo **ViaCEP** para
consulta de endereços e se comunica com o microserviço **distance-service**
para calcular distâncias entre coordenadas.

Componentes da arquitetura:
- **visitas-api** → API principal
- **distance-service** → microsserviço de cálculo de distância
- **ViaCEP** → serviço externo público
""",
)

# Tags da documentação
tags_metadata = [
    {"name": "Visitas", "description": "CRUD completo de visitas técnicas."},
    {"name": "Endereços", "description": "Integração com serviço externo ViaCEP."},
    {"name": "Distância", "description": "Cálculo de distância via distance-service."},
    {"name": "Sistema", "description": "Rotas internas e de diagnóstico da API."},
]

app.openapi_tags = tags_metadata

# Banco de Dados
def init_db():
    conn = sqlite3.connect(DB)
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

def row_to_dict(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

init_db()

# Modelos Pydantic
class Location(BaseModel):
    lat: float = Field(..., example=-19.9232)
    lon: float = Field(..., example=-43.9419)

class VisitIn(BaseModel):
    title: str = Field(..., example="Visita Técnica - Mina X", description="Título da visita.")
    description: Optional[str] = Field(None, example="Inspeção de rotina")
    date: Optional[str] = Field(None, example="2025-01-10T14:00:00", description="Data em formato ISO")
    cep: Optional[str] = Field(None, example="30140071")
    address: Optional[str] = Field(None, example="Av. Afonso Pena, 1500")
    lat: Optional[float] = Field(None, example=-19.9232)
    lon: Optional[float] = Field(None, example=-43.9419)
    responsible: Optional[str] = Field(None, example="Carlos Alberto")

class DistanceCheckRequest(BaseModel):
    origin: Location
    destination: Location

# Rotas
@app.post(
    "/visits",
    status_code=status.HTTP_201_CREATED,
    tags=["Visitas"],
    summary="Registrar uma nova visita",
    description="Cria uma nova visita no banco e retorna seu ID.",
)
def create_visit(payload: VisitIn):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO visits (title, description, date, cep, address, lat, lon, responsible, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.title, payload.description, payload.date, payload.cep, payload.address,
        payload.lat, payload.lon, payload.responsible, "scheduled", now, now
    ))
    conn.commit()
    vid = cur.lastrowid
    conn.close()
    return {"id": vid}

@app.get(
    "/visits",
    tags=["Visitas"],
    summary="Listar visitas",
    description="Lista todas as visitas cadastradas, com paginação opcional.",
    response_model=List[dict]
)
def list_visits(page: int = 1, size: int = 50, status: Optional[str] = None):
    offset = (page - 1) * size
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    if status:
        cur.execute("SELECT * FROM visits WHERE status = ? ORDER BY date LIMIT ? OFFSET ?", (status, size, offset))
    else:
        cur.execute("SELECT * FROM visits ORDER BY date LIMIT ? OFFSET ?", (size, offset))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    result = [dict(zip(cols, r)) for r in rows]
    conn.close()
    return result

@app.get(
    "/visits/{visit_id}",
    tags=["Visitas"],
    summary="Buscar visita por ID",
    description="Retorna os dados completos de uma visita.",
)
def get_visit(visit_id: int = Path(..., gt=0)):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM visits WHERE id = ?", (visit_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Visit not found")
    cols = [d[0] for d in cur.description]
    result = dict(zip(cols, row))
    conn.close()
    return result

@app.put(
    "/visits/{visit_id}",
    tags=["Visitas"],
    summary="Atualizar uma visita",
    description="Atualiza todos os campos de uma visita existente.",
)
def update_visit(visit_id: int, payload: VisitIn):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
      UPDATE visits SET title=?, description=?, date=?, cep=?, address=?,
      lat=?, lon=?, responsible=?, updated_at=? WHERE id=?
    """, (
        payload.title, payload.description, payload.date, payload.cep,
        payload.address, payload.lat, payload.lon, payload.responsible,
        now, visit_id
    ))
    conn.commit()
    conn.close()
    return {"ok": True, "id": visit_id}

@app.delete(
    "/visits/{visit_id}",
    tags=["Visitas"],
    summary="Excluir uma visita",
    description="Remove uma visita do banco de dados.",
)
def delete_visit(visit_id: int):
    conn = sqlite3.connect(DB)
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
    description="Consulta o serviço público ViaCEP e retorna endereço normalizado.",
)
def via_cep(cep: str):
    cep_clean = "".join(filter(str.isdigit, cep))
    url = f"https://viacep.com.br/ws/{cep_clean}/json/"

    try:
        r = httpx.get(url, timeout=10)
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao acessar ViaCEP")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="ViaCEP retornou erro")

    data = r.json()
    if data.get("erro"):
        raise HTTPException(status_code=404, detail="CEP não encontrado")

    return {
        "cep": data.get("cep"),
        "logradouro": data.get("logradouro"),
        "bairro": data.get("bairro"),
        "localidade": data.get("localidade"),
        "uf": data.get("uf")
    }

# Integração com distance-service
@app.post(
    "/visits/{visit_id}/distance-check",
    tags=["Distância"],
    summary="Calcular distância entre dois pontos",
    description="""
Consulta o **distance-service** para calcular a distância entre duas coordenadas.

- Entrada: latitude/longitude de origem e destino  
- Saída: distância em quilômetros  
""",
)
def distance_check(visit_id: int, payload: DistanceCheckRequest):
    url = f"{DISTANCE_SERVICE_URL}/distance"

    try:
        r = httpx.post(
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

# Check de Health
@app.get(
    "/health",
    tags=["Sistema"],
    summary="Verificar status da API",
    description="Retorna informações básicas de saúde do serviço.",
)
def health():
    return {"status": "ok", "service": "visitas-api"}
