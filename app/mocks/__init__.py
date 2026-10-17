"""
Sub-aplicacion con las tres APIs simuladas. Se monta en /mock dentro de la app principal.
Documentacion interactiva (Swagger): /mock/docs  -> boton "Authorize" para ingresar la API key.
"""
from fastapi import FastAPI

from app.mocks import athenea, imedical, sagicc

mock_app = FastAPI(
    title="APIs simuladas - Athenea, iMedical y SAGICC",
    description="Servicios REST ficticios que imitan los sistemas de la IPS Carvajal. "
                "Cada sistema exige su propia API key en el header `x-api-key`.",
    version="1.0.0",
)
mock_app.include_router(athenea.router)
mock_app.include_router(imedical.router)
mock_app.include_router(sagicc.router)
