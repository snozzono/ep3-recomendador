from datetime import datetime

from pydantic import BaseModel, Field


class InteraccionIn(BaseModel):
    usuario: str = Field(min_length=1)
    producto: str = Field(min_length=1)
    rating: float = Field(ge=1, le=5)
    timestamp: datetime


class Recomendacion(BaseModel):
    parent_asin: str
    score: float


class RecomendacionOut(BaseModel):
    usuario: str
    recomendaciones: list[Recomendacion]
    modelo: str


class AceptadoOut(BaseModel):
    estado: str


class SaludOut(BaseModel):
    estado: str
