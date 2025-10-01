# main.py
import os # Import para ler variáveis de ambiente
from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, ConfigDict
from typing import List
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware # Import do CORS

# --- 1. CONFIGURAÇÃO DO BANCO DE DADOS (Agora com variável de ambiente) ---
# Pega a URL do banco da variável de ambiente 'DATABASE_URL'
DATABASE_URL = os.environ.get("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 2. MODELOS DA TABELA E DA API (continuam os mesmos) ---
class LocationDB(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

class AlertDB(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    category = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    timestamp = Column(DateTime, server_default='now()')

class Location(BaseModel):
    latitude: float
    longitude: float
    model_config = ConfigDict(from_attributes=True)

class Alert(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timestamp: datetime | None = None
    model_config = ConfigDict(from_attributes=True)

# --- 3. INICIALIZAÇÃO DA API ---
app = FastAPI()

# --- 4. CONFIGURAÇÃO DO CORS ---
# Permite que qualquer origem (incluindo Zapp.run) acesse sua API
origins = ["*"] # Em produção real, você listaria os domínios permitidos

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 5. ENDPOINTS (continuam os mesmos) ---
@app.get("/")
def read_root():
    return {"message": "Bem-vindo à API! Acesse /locations ou /alerts"}

@app.get("/locations", response_model=List[Location])
def read_locations(db: Session = Depends(get_db)):
    return db.query(LocationDB).all()

@app.get("/alerts", response_model=List[Alert])
def read_alerts(db: Session = Depends(get_db)):
    return db.query(AlertDB).order_by(AlertDB.timestamp.desc()).all()