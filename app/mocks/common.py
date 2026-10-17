"""Utilidades compartidas por las APIs simuladas."""
from __future__ import annotations

import asyncio
import random
from datetime import date

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import hoy, settings

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False,
                              description="API key del sistema (Athenea, iMedical o SAGICC)")


def require_api_key(sistema: str):
    """Dependencia FastAPI: valida el header x-api-key del sistema indicado y simula latencia."""

    async def _validar(x_api_key: str | None = Security(api_key_header)) -> None:
        if settings.mock_latency_ms:
            await asyncio.sleep(random.uniform(0.4, 1.0) * settings.mock_latency_ms / 1000)
        esperado = getattr(settings, f"{sistema}_api_key")
        if not x_api_key or x_api_key != esperado:
            raise HTTPException(status_code=401, detail=f"API key invalida o ausente para {sistema.capitalize()}")

    return Depends(_validar)


def edad(fecha_nacimiento: str) -> int:
    fn, ref = date.fromisoformat(fecha_nacimiento), hoy()
    return ref.year - fn.year - ((ref.month, ref.day) < (fn.month, fn.day))
