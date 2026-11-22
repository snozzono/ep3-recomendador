from datetime import datetime

from pydantic import BaseModel, Field


class InteraccionIn(BaseModel):
    usuario: int = Field(ge=0)
    producto: int = Field(ge=0)
    rating: float = Field(ge=1, le=5)
    timestamp: datetime


class RecomendacionOut(BaseModel):
    usuario: int
    recomendaciones: list[int]
    modelo: str


class AceptadoOut(BaseModel):
    estado: str


class SaludOut(BaseModel):
    estado: str
