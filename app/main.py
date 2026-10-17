"""
Punto de entrada principal de la aplicación FastAPI (Copiloto IPS Carvajal).
Sirve:
  - APIs simuladas en /mock (con OpenAPI Swagger en /mock/docs)
  - Endpoint del Agente Copiloto en /api/chat
  - Endpoints de Autoservicio para Agendamiento Web en /api/self-service/*
  - Endpoint de Ficha Unificada 360 en /api/patient-360/*
  - Frontend web interactivo en /
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent import procesar_mensaje
from app.clients import ApiClient
from app.config import PUBLIC_DIR, settings
from app.mocks import mock_app
from app.tools import ejecutar_tool

app = FastAPI(
    title="IPS Carvajal - Copiloto de Atención & Agendamiento",
    description="Plataforma de IA y automatización para optimización de tiempos de atención y autoservicio omnicanal.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar las APIs simuladas de Athenea, iMedical y SAGICC
app.mount("/mock", mock_app)

# -----------------------------------------------------------------------------
# Modelos para la API del Chat
# -----------------------------------------------------------------------------
class MensajeChat(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)

class SolicitudReservaWeb(BaseModel):
    numero_documento: str
    id_slot: str
    canal_origen: str = "Web Autoservicio"
    atencion_particular: bool = False
    observaciones: str | None = None

class SolicitudCancelarWeb(BaseModel):
    id_slot: str | None = None
    numero_documento: str | None = None
    id_cita: str | None = None
    motivo: str = "Cancelación desde autoservicio web"

class SolicitudRegistrarPaciente(BaseModel):
    tipo_documento: str = "CC"
    numero_documento: str
    primer_nombre: str
    segundo_nombre: str | None = None
    primer_apellido: str
    segundo_apellido: str | None = None
    fecha_nacimiento: str
    sexo: str | None = "M"
    telefono: str | None = None
    email: str | None = None
    direccion: str | None = None
    municipio: str | None = "Tunja"
    eps: str | None = "Particular"
    empresa: str | None = None
    acepta_whatsapp: bool = True

class SolicitudActualizarPaciente(BaseModel):
    telefono: str | None = None
    email: str | None = None
    direccion: str | None = None
    municipio: str | None = None
    eps: str | None = None
    empresa: str | None = None
    acepta_whatsapp: bool | None = None

# -----------------------------------------------------------------------------
# Endpoints del Copiloto
# -----------------------------------------------------------------------------
@app.post("/api/chat", summary="Conversar con el Copiloto de IA")
async def chat_endpoint(body: MensajeChat):
    if not body.message.strip():
        raise HTTPException(400, "El mensaje no puede estar vacío")
    resultado = await procesar_mensaje(body.history, body.message)
    return resultado

@app.get("/api/patient-360/{numero_documento}", summary="Ficha Unificada 360 del Paciente")
async def ficha_360_endpoint(numero_documento: str):
    """
    Consulta Athenea, iMedical y SAGICC en paralelo y unifica la información
    en una sola pantalla para eliminar el dolor de 'saltar entre 3 sistemas'.
    """
    async with ApiClient() as api:
        res_pac, _ = await ejecutar_tool(api, "buscar_paciente", {"numero_documento": numero_documento})
        if res_pac.get("error"):
            raise HTTPException(404, "Paciente no encontrado en Athenea")

        res_aut, _ = await ejecutar_tool(api, "consultar_autorizaciones", {"numero_documento": numero_documento})
        res_lab, _ = await ejecutar_tool(api, "consultar_resultados_laboratorio", {"numero_documento": numero_documento})
        res_cit, _ = await ejecutar_tool(api, "consultar_citas_paciente", {"numero_documento": numero_documento})
        res_his, _ = await ejecutar_tool(api, "consultar_historia_resumen", {"numero_documento": numero_documento})
        res_int, _ = await ejecutar_tool(api, "historial_interacciones", {"numero_documento": numero_documento, "limite": 5})
        res_pq, _ = await ejecutar_tool(api, "consultar_pqrs", {"numero_documento": numero_documento})

        return {
            "athenea": {
                "paciente": res_pac.get("data"),
                "autorizaciones": res_aut.get("data", []),
                "resultados_laboratorio": res_lab.get("data", []),
            },
            "imedical": {
                "citas": res_cit.get("resultado", []),
                "historia_clinica": res_his.get("resultado", {}),
            },
            "sagicc": {
                "interacciones": res_int.get("data", []),
                "pqrs": res_pq.get("data", []),
            }
        }

@app.post("/api/patients", summary="Registrar nuevo paciente en Athenea")
async def registrar_paciente_endpoint(body: SolicitudRegistrarPaciente):
    async with ApiClient() as api:
        res, traza = await ejecutar_tool(api, "registrar_paciente", body.model_dump())
        if res.get("error"):
            raise HTTPException(traza.get("status", 400), res.get("detalle") or "Error registrando paciente")
        return res

@app.patch("/api/patients/{numero_documento}", summary="Actualizar datos de paciente en Athenea")
async def actualizar_paciente_endpoint(numero_documento: str, body: SolicitudActualizarPaciente):
    async with ApiClient() as api:
        payload = {"numero_documento": numero_documento, **body.model_dump(exclude_unset=True)}
        res, traza = await ejecutar_tool(api, "actualizar_datos_paciente", payload)
        if res.get("error"):
            raise HTTPException(traza.get("status", 400), res.get("detalle") or "Error actualizando paciente")
        return res

# -----------------------------------------------------------------------------
# Endpoints de Autoservicio Web (Para https://laboratoriocarvajal.com/)
# -----------------------------------------------------------------------------
@app.get("/api/self-service/catalog", summary="Catálogo para agendamiento web")
async def catalogo_web():
    async with ApiClient() as api:
        status, data, _ = await api.request("imedical", "GET", "/imedical/api/v2/especialidades")
        status_sedes, data_sedes, _ = await api.request("imedical", "GET", "/imedical/api/v2/sedes")
        return {
            "especialidades": data.get("resultado", []),
            "sedes": data_sedes.get("resultado", []),
        }

@app.get("/api/self-service/availability", summary="Consulta de cupos libres para el paciente")
@app.get("/api/self-service/disponibilidad", summary="Consulta de cupos libres (alias español)")
async def disponibilidad_web(especialidad: str, sede: str | None = None):
    async with ApiClient() as api:
        res, _ = await ejecutar_tool(api, "consultar_disponibilidad", {
            "especialidad": especialidad,
            "sede": sede,
            "limite": 8
        })
        return res

@app.post("/api/self-service/book", summary="Agendar cita desde la web de autoservicio")
@app.post("/api/self-service/reservar", summary="Agendar cita (alias español)")
async def reservar_cita_web(body: SolicitudReservaWeb):
    async with ApiClient() as api:
        res, traza = await ejecutar_tool(api, "agendar_cita", {
            "numero_documento": body.numero_documento,
            "id_slot": body.id_slot,
            "canal_origen": "Web Autoservicio Carvajal",
            "atencion_particular": body.atencion_particular,
            "observaciones": body.observaciones or "Agendada desde portal web"
        })
        if res.get("error"):
            raise HTTPException(res.get("status", 400), res.get("detalle"))
        return res

@app.post("/api/self-service/cancel", summary="Cancelar cita o liberar cupo desde autoservicio")
@app.post("/api/self-service/cancelar", summary="Cancelar cita o liberar cupo (alias español)")
async def cancelar_cita_web(body: SolicitudCancelarWeb):
    async with ApiClient() as api:
        res, traza = await ejecutar_tool(api, "liberar_cupo", {
            "id_slot": body.id_slot,
            "numero_documento": body.numero_documento,
            "id_cita": body.id_cita,
            "motivo": body.motivo
        })
        if res.get("error"):
            raise HTTPException(res.get("status", 400), res.get("detalle"))
        return res

# -----------------------------------------------------------------------------
# Métricas y KPIs de Contact Center (Demostración de ahorros)
# -----------------------------------------------------------------------------
@app.get("/api/metrics/kpis", summary="Métricas de reducción de tiempos y autonomía")
async def metricas_kpi():
    async with ApiClient() as api:
        status, data, _ = await api.request("sagicc", "GET", "/sagicc/api/v1/metricas", params={"dias": 7})
        return data.get("data", {})

# -----------------------------------------------------------------------------
# Servir Frontend
# -----------------------------------------------------------------------------
if PUBLIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=PUBLIC_DIR), name="static")

@app.get("/", response_class=FileResponse)
async def home_page():
    index_path = PUBLIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>IPS Carvajal - Copiloto API en ejecución</h1><p>Visita /docs para la documentación interactiva.</p>")
