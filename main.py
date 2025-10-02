# main.py
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import logging

# --- CONFIGURAÇÃO DE LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL não está configurada nas variáveis de ambiente")

# Adiciona pool de conexões e configurações de timeout
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verifica conexões antes de usar
    pool_size=10,  # Número de conexões no pool
    max_overflow=20,  # Conexões extras permitidas
    echo=False  # Mude para True para debug SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELOS DA TABELA (SQLAlchemy) ---
class AlertDB(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)  # Limite de caracteres e índice
    description = Column(String(1000))  # Limite de caracteres
    category = Column(String(100), index=True)  # Índice para filtros
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timestamp = Column(DateTime, server_default='now()', nullable=False)
    bairro = Column(String(100))
    
    # Índice composto para consultas geoespaciais
    __table_args__ = (
        Index('idx_location', 'latitude', 'longitude'),
        Index('idx_timestamp_category', 'timestamp', 'category'),
    )

# --- MODELOS DE DADOS DA API (Pydantic) ---
class AlertCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Título do alerta")
    description: str = Field(..., max_length=1000, description="Descrição detalhada")
    category: str = Field(..., max_length=100, description="Categoria do alerta")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude (-90 a 90)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude (-180 a 180)")
    bairro: str

class Alert(AlertCreate):
    id: int
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

class AlertResponse(BaseModel):
    """Resposta para operações de alerta"""
    success: bool
    message: str
    data: Optional[Alert] = None

# --- LIFESPAN PARA CRIAR TABELAS ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia inicialização e finalização da aplicação"""
    logger.info("Iniciando aplicação...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Tabelas criadas/verificadas com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar tabelas: {e}")
        raise
    
    yield
    
    logger.info("Encerrando aplicação...")
    engine.dispose()

# --- INICIALIZAÇÃO DA API ---
app = FastAPI(
    title="API de Alertas",
    description="API para gerenciamento de alertas geográficos",
    version="1.0.0",
    lifespan=lifespan
)

# CORS mais restritivo (ajuste conforme necessário)
origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# --- DEPENDÊNCIA DE BANCO DE DADOS ---
def get_db():
    """Gerencia sessões do banco de dados"""
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Erro de banco de dados: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao acessar o banco de dados"
        )
    finally:
        db.close()

# --- ENDPOINTS ---
@app.get("/", tags=["Health"])
def read_root():
    """Endpoint de health check"""
    return {
        "message": "API de Alertas está no ar!",
        "version": "1.0.0",
        "status": "healthy"
    }

@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Verifica saúde da API e conexão com banco"""
    try:
        # Testa conexão com banco
        db.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check falhou: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço indisponível"
        )

@app.get("/alerts", response_model=List[Alert], tags=["Alerts"])
def read_alerts(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Lista alertas com paginação e filtros
    
    - **skip**: Número de registros para pular (padrão: 0)
    - **limit**: Número máximo de registros (padrão: 100, máx: 1000)
    - **category**: Filtrar por categoria (opcional)
    """
    try:
        # Limita o máximo de registros
        limit = min(limit, 1000)
        
        query = db.query(AlertDB).order_by(AlertDB.timestamp.desc())
        
        # Filtro por categoria
        if category:
            query = query.filter(AlertDB.category == category)
        
        alerts = query.offset(skip).limit(limit).all()
        return alerts
    except SQLAlchemyError as e:
        logger.error(f"Erro ao buscar alertas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar alertas"
        )

@app.get("/alerts/{alert_id}", response_model=Alert, tags=["Alerts"])
def read_alert(alert_id: int, db: Session = Depends(get_db)):
    """Busca um alerta específico por ID"""
    alert = db.query(AlertDB).filter(AlertDB.id == alert_id).first()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alerta com ID {alert_id} não encontrado"
        )
    
    return alert

@app.post(
    "/alerts",
    response_model=Alert,
    status_code=status.HTTP_201_CREATED,
    tags=["Alerts"]
)
def create_alert(alert: AlertCreate, db: Session = Depends(get_db)):
    """
    Cria um novo alerta
    
    Validações automáticas:
    - Título: 1-255 caracteres
    - Descrição: máximo 1000 caracteres
    - Latitude: -90 a 90
    - Longitude: -180 a 180
    """
    try:
        db_alert = AlertDB(**alert.model_dump())
        db.add(db_alert)
        db.commit()
        db.refresh(db_alert)
        
        logger.info(f"Alerta criado: ID {db_alert.id}")
        return db_alert
    
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Erro ao criar alerta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar alerta"
        )

@app.delete("/alerts/{alert_id}", tags=["Alerts"])
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """Deleta um alerta por ID"""
    alert = db.query(AlertDB).filter(AlertDB.id == alert_id).first()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alerta com ID {alert_id} não encontrado"
        )
    
    try:
        db.delete(alert)
        db.commit()
        logger.info(f"Alerta deletado: ID {alert_id}")
        return {"message": f"Alerta {alert_id} deletado com sucesso"}
    
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Erro ao deletar alerta: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar alerta"
        )

@app.get("/alerts/nearby", response_model=List[Alert], tags=["Alerts"])
def get_nearby_alerts(
    latitude: float = Field(..., ge=-90, le=90),
    longitude: float = Field(..., ge=-180, le=180),
    radius_km: float = Field(5.0, gt=0, le=100),
    db: Session = Depends(get_db)
):
    """
    Busca alertas próximos a uma localização
    
    Usa aproximação simples (não é perfeita para grandes distâncias)
    - **radius_km**: Raio de busca em km (padrão: 5km, máximo: 100km)
    """
    # Aproximação: 1 grau ≈ 111 km
    degree_radius = radius_km / 111.0
    
    alerts = db.query(AlertDB).filter(
        AlertDB.latitude.between(latitude - degree_radius, latitude + degree_radius),
        AlertDB.longitude.between(longitude - degree_radius, longitude + degree_radius)
    ).order_by(AlertDB.timestamp.desc()).limit(100).all()
    
    return alerts
