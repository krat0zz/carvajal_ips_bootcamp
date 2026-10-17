"""Configuracion central leida desde variables de entorno (.env en local, Vercel en la nube)."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = ROOT_DIR / "data" / "generated"
DOCS_DIR = ROOT_DIR / "data" / "docs"
PUBLIC_DIR = ROOT_DIR / "public"

# Colombia no tiene horario de verano: UTC-5 fijo (evita depender de tzdata en Windows).
TZ_COLOMBIA = timezone(timedelta(hours=-5), name="America/Bogota")


class Settings:
    def __init__(self) -> None:
        # LLM (Google Gemini)
        self.gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        self.embedding_model: str = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

        # API keys de los sistemas simulados (cada "proveedor" tiene su propia llave)
        self.athenea_api_key: str = os.getenv("ATHENEA_API_KEY", "athenea-dev-key")
        self.imedical_api_key: str = os.getenv("IMEDICAL_API_KEY", "imedical-dev-key")
        self.sagicc_api_key: str = os.getenv("SAGICC_API_KEY", "sagicc-dev-key")

        # Si se define, el copiloto llama a las APIs por HTTP real (p. ej. https://mi-app.vercel.app).
        # Vacio = llamada HTTP en proceso (misma app), util en local y en serverless.
        self.mock_base_url: str = os.getenv("MOCK_API_BASE_URL", "").strip()
        self.mock_latency_ms: int = int(os.getenv("MOCK_LATENCY_MS", "0"))

        # Codigo de acceso opcional para proteger el chat publicado (evita gastar la API key).
        self.access_code: str = os.getenv("APP_ACCESS_CODE", "").strip()

        # Permite fijar el "hoy" (AAAA-MM-DD) para pruebas reproducibles.
        self.hoy_simulado: str | None = os.getenv("HOY_SIMULADO") or None

    @property
    def llm_configurado(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()


def ahora() -> datetime:
    if settings.hoy_simulado:
        d = date.fromisoformat(settings.hoy_simulado)
        return datetime(d.year, d.month, d.day, 8, 0, tzinfo=TZ_COLOMBIA)
    return datetime.now(TZ_COLOMBIA)


def hoy() -> date:
    return ahora().date()
