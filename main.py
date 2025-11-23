# main.py
from fastapi import FastAPI, HTTPException, status, Path
from pydantic import BaseModel, Field
from typing import Optional, List
import sqlite3
import httpx
from datetime import datetime
import os

DB = os.getenv("VISITAS_DB", "visitas.db")

app = FastAPI(title="visitas-api - VisitaUp", version="1.0.0")

# ---------- DB util ----------
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

# ---------- Pydantic models ----------
class Location(BaseModel):
    lat: float
    lon: float

class VisitIn(BaseModel):
    title: str = Field(..., example="Visita Técnica - Mina X")
    description: Optional[str] = None
    date: Optional[str] = None  # ISO string
    cep: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    responsible: Optional[str] = None

class DistanceCheckRequest(BaseModel):
    origin: Location
    destination: Location

# ---------- CRUD endpoints ----------
@app.post("/visits", status_code=status.HTTP_201_CREATED)
def create_visit(payload: VisitIn):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO visits (title, description, date, cep, address, lat, lon, responsible, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (payload.title, payload.description, payload.date, payload.cep, payload.address, payload.lat, payload.lon, payload.responsible, 'scheduled', now, now))
    conn.commit()
    vid = cur.lastrowid
    conn.close()
    return {"id": vid}

@app.get("/visits", response_model=List[dict])
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

@app.get("/visits/{visit_id}")
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

@app.put("/visits/{visit_id}")
def update_visit(visit_id: int, payload: VisitIn):
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
      UPDATE visits SET title=?, description=?, date=?, cep=?, address=?, lat=?, lon=?, responsible=?, updated_at=?
      WHERE id=?
    """, (payload.title, payload.description, payload.date, payload.cep, payload.address, payload.lat, payload.lon, payload.responsible, now, visit_id))
    conn.commit()
    conn.close()
    return {"ok": True, "id": visit_id}

@app.delete("/visits/{visit_id}")
def delete_visit(visit_id: int):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM visits WHERE id = ?", (visit_id,))
    conn.commit()
    conn.close()
    return {"deleted": visit_id}

# ---------- ViaCEP integration ----------
@app.get("/address/cep/{cep}")
def via_cep(cep: str):
    cep_clean = ''.join(filter(str.isdigit, cep))
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
    # Retorna dados normalizados
    return {
        "cep": data.get("cep"),
        "logradouro": data.get("logradouro"),
        "bairro": data.get("bairro"),
        "localidade": data.get("localidade"),
        "uf": data.get("uf")
    }

# ---------- Distance check (calls distance-service) ----------
DISTANCE_SERVICE_URL = os.getenv("DISTANCE_SERVICE_URL", "http://distance-service:5000")

@app.post("/visits/{visit_id}/distance-check")
def distance_check(visit_id: int, payload: DistanceCheckRequest):
    url = f"{DISTANCE_SERVICE_URL}/distance"
    try:
        r = httpx.post(url, json={"from": payload.origin.dict(), "to": payload.destination.dict()}, timeout=10)
    except Exception:
        raise HTTPException(status_code=502, detail="Erro ao contatar distance-service")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="distance-service retornou erro")
    return r.json()

# ---------- Health ----------
@app.get("/health")
def health():
    return {"status": "ok", "service": "visitas-api"}