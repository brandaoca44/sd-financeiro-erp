from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.database.health import is_database_available

router = APIRouter(prefix="/health", tags=["Saúde"])

class HealthResponse(BaseModel):
    """Representa o estado público dos componentes da aplicação."""

    status: Literal["healthy", "unhealthy"]


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Verificar a disponibilidade da API",
)
async def get_health(response: Response) -> HealthResponse:
    """Verifica a disponibilidade da API e do PostgreSQL."""

    database_available = await is_database_available()
    response.headers["Cache-Control"] = "no-store"

    if not database_available:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="healthy" if database_available else "unhealthy",
    )
