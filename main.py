# main.py
import os
from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, ConfigDict
from typing import List
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELOS DA TABELA (SQLAlchemy) ---
class AlertDB(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    category = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    timestamp = Column(DateTime, server_default='now()')

# --- MODELOS DE DADOS DA API (Pydantic) ---
# Modelo para criar um novo alerta (o que recebemos do formulário)
class AlertCreate(BaseModel):
    title: str
    description: str
    category: str
    latitude: float
    longitude: float

# Modelo para retornar um alerta (o que enviamos para o Flutter)
class Alert(AlertCreate):
    id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

# --- INICIALIZAÇÃO DA API ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- ENDPOINTS ---
@app.get("/")
def read_root():
    return {"message": "API de Alertas está no ar!"}

@app.get("/alerts", response_model=List[Alert])
def read_alerts(db: Session = Depends(get_db)):
    return db.query(AlertDB).order_by(AlertDB.timestamp.desc()).all()

# --- NOVO ENDPOINT PARA CRIAR ALERTAS ---
@app.post("/alerts", response_model=Alert)
def create_alert(alert: AlertCreate, db: Session = Depends(get_db)):
    # Converte o dado recebido (Pydantic) para o modelo do banco (SQLAlchemy)
    db_alert = AlertDB(**alert.model_dump())
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert
