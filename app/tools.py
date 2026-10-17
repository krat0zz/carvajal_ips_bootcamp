"""
Capa de herramientas (tools) que el LLM puede invocar.

Cada tool encapsula una llamada a la API de un sistema (Athenea, iMedical, SAGICC)
o a la base documental (RAG). Esta misma capa puede reutilizarse en otros canales
(formulario web, bot de WhatsApp) sin cambiar nada.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app import rag
from app.clients import ApiClient
from app.data_store import solo_digitos

S, I, B, O = "STRING", "INTEGER", "BOOLEAN", "OBJECT"


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": O, "properties": props, "required": required or []}


DOC = {"type": S, "description": "Numero de documento del paciente (solo digitos, sin puntos)"}


@dataclass
class Tool:
    name: str
    description: str
    sistema: str
    parameters: dict
    run: Callable[[ApiClient, dict], Awaitable[tuple[int, Any, dict]]]


def _call(sistema: str, metodo: str, ruta: str, params_fn=None, body_fn=None):
    """Crea el ejecutor de una tool que llama a un endpoint REST."""

    async def run(api: ApiClient, args: dict):
        r = ruta.format(**{k: (solo_digitos(v) if k == "numero_documento" else v) for k, v in args.items()})
        params = params_fn(args) if params_fn else None
        body = body_fn(args) if body_fn else None
        status, data, ms = await api.request(sistema, metodo, r, params=params, json=body)
        return status, data, {"metodo": metodo, "endpoint": r, "params": params or body, "ms": round(ms, 1)}

    return run


async def _rag(api: ApiClient, args: dict):
    import time

    t0 = time.perf_counter()
    res = await rag.buscar(args["pregunta"], k=4)
    data = {"metodo_busqueda": res["metodo"],
            "fragmentos": [{"documento": f["documento"], "seccion": f["seccion"], "texto": f["texto"],
                            "puntaje": f["puntaje"]} for f in res["fragmentos"]]}
    return 200, data, {"metodo": "SEARCH", "endpoint": "rag://data/docs", "params": args,
                       "ms": round((time.perf_counter() - t0) * 1000, 1)}


def _doc(a: dict) -> dict:
    return {"numero_documento": solo_digitos(a["numero_documento"])}


TOOLS: list[Tool] = [
    # ------------------------------ Athenea ------------------------------
    Tool("buscar_paciente",
         "Athenea. Datos demograficos y de afiliacion del paciente (EPS, regimen, categoria, estado de afiliacion, "
         "telefono, correo, municipio). Usar SIEMPRE primero cuando se mencione un documento.",
         "Athenea", _obj({"numero_documento": DOC}, ["numero_documento"]),
         _call("athenea", "GET", "/athenea/api/v1/pacientes/{numero_documento}")),
    Tool("buscar_paciente_por_nombre",
         "Athenea. Busca pacientes por nombre y/o apellidos cuando no se conoce el documento.",
         "Athenea", _obj({"nombre": {"type": S, "description": "Nombre y/o apellidos"}}, ["nombre"]),
         _call("athenea", "GET", "/athenea/api/v1/pacientes", lambda a: {"nombre": a["nombre"]})),
    Tool("consultar_autorizaciones",
         "Athenea. Autorizaciones de servicios emitidas por la EPS del paciente (VIGENTE, VENCIDA, UTILIZADA, "
         "PENDIENTE, NEGADA) con especialidad y fecha de vencimiento.",
         "Athenea", _obj({"numero_documento": DOC}, ["numero_documento"]),
         _call("athenea", "GET", "/athenea/api/v1/autorizaciones", _doc)),
    Tool("consultar_tarifas",
         "Athenea. Tarifas de consultas y examenes por servicio y entidad (EPS o Particular).",
         "Athenea", _obj({"servicio": {"type": S, "description": "Ej: 'medicina interna', 'hemograma', 'glucosa'"},
                          "entidad": {"type": S, "description": "Ej: 'Particular', 'Nueva EPS', 'Sanitas'"}}),
         _call("athenea", "GET", "/athenea/api/v1/tarifas",
               lambda a: {"servicio": a.get("servicio"), "entidad": a.get("entidad")})),
    Tool("consultar_cuotas_moderadoras",
         "Athenea. Tabla de cuotas moderadoras y copagos por regimen y categoria.",
         "Athenea", _obj({}),
         _call("athenea", "GET", "/athenea/api/v1/cuotas-moderadoras")),
    Tool("consultar_resultados_laboratorio",
         "Athenea (modulo de laboratorio). Ordenes de laboratorio del paciente: examenes, fecha de toma, "
         "estado del resultado (EN_PROCESO, LISTO, ENTREGADO), fecha estimada y canal de entrega. No incluye valores.",
         "Athenea", _obj({"numero_documento": DOC}, ["numero_documento"]),
         _call("athenea", "GET", "/athenea/api/v1/laboratorio/resultados", _doc)),
    Tool("consultar_examenes_laboratorio",
         "Athenea (modulo de laboratorio). Catalogo de examenes con codigo y valor particular.",
         "Athenea", _obj({"nombre": {"type": S, "description": "Filtro opcional por nombre del examen"}}),
         _call("athenea", "GET", "/athenea/api/v1/laboratorio/examenes", lambda a: {"nombre": a.get("nombre")})),
    Tool("registrar_paciente",
         "Athenea. Registra o ingresa un nuevo paciente en la IPS (en Athenea). "
         "Requiere numero_documento, primer_nombre, primer_apellido y fecha_nacimiento (AAAA-MM-DD).",
         "Athenea", _obj({
             "numero_documento": DOC,
             "tipo_documento": {"type": S, "description": "Tipo de documento (CC, TI, CE, RC, etc.)"},
             "primer_nombre": {"type": S, "description": "Primer nombre del paciente"},
             "segundo_nombre": {"type": S, "description": "Segundo nombre (opcional)"},
             "primer_apellido": {"type": S, "description": "Primer apellido del paciente"},
             "segundo_apellido": {"type": S, "description": "Segundo apellido (opcional)"},
             "fecha_nacimiento": {"type": S, "description": "Fecha de nacimiento en formato AAAA-MM-DD"},
             "sexo": {"type": S, "description": "Sexo: M o F"},
             "telefono": {"type": S, "description": "Numero de telefono o celular"},
             "email": {"type": S, "description": "Correo electronico"},
             "direccion": {"type": S, "description": "Direccion de residencia"},
             "municipio": {"type": S, "description": "Municipio (ej: Tunja, Duitama, Sogamoso)"},
             "eps": {"type": S, "description": "EPS del paciente (ej: Nueva EPS, Sanitas, Particular)"},
             "empresa": {"type": S, "description": "Empresa para convenio o salud ocupacional (opcional)"},
         }, ["numero_documento", "primer_nombre", "primer_apellido", "fecha_nacimiento"]),
         _call("athenea", "POST", "/athenea/api/v1/pacientes", body_fn=lambda a: {
             "tipo_documento": a.get("tipo_documento", "CC"),
             "numero_documento": solo_digitos(a["numero_documento"]),
             "primer_nombre": a["primer_nombre"],
             "segundo_nombre": a.get("segundo_nombre"),
             "primer_apellido": a["primer_apellido"],
             "segundo_apellido": a.get("segundo_apellido"),
             "fecha_nacimiento": a["fecha_nacimiento"],
             "sexo": a.get("sexo", "M"),
             "telefono": a.get("telefono"),
             "email": a.get("email"),
             "direccion": a.get("direccion"),
             "municipio": a.get("municipio", "Tunja"),
             "eps": a.get("eps", "Particular"),
             "empresa": a.get("empresa"),
         })),
    Tool("actualizar_datos_paciente",
         "Athenea. Modifica o actualiza datos demograficos o de contacto de un paciente existente "
         "(telefono, email, direccion, municipio, empresa, eps, acepta_whatsapp).",
         "Athenea", _obj({
             "numero_documento": DOC,
             "telefono": {"type": S, "description": "Nuevo numero de telefono o celular"},
             "email": {"type": S, "description": "Nuevo correo electronico"},
             "direccion": {"type": S, "description": "Nueva direccion de residencia"},
             "municipio": {"type": S, "description": "Nuevo municipio"},
             "empresa": {"type": S, "description": "Nueva empresa o convenio laboral"},
             "eps": {"type": S, "description": "Nueva EPS"},
             "acepta_whatsapp": {"type": B, "description": "Si autoriza contacto por WhatsApp"},
         }, ["numero_documento"]),
         _call("athenea", "PATCH", "/athenea/api/v1/pacientes/{numero_documento}", body_fn=lambda a: {
             k: v for k, v in a.items() if k != "numero_documento" and v is not None
         })),
    # ------------------------------ iMedical ------------------------------
    Tool("listar_especialidades",
         "iMedical. Especialidades disponibles, sedes donde se ofrecen, duracion y si requieren autorizacion de EPS.",
         "iMedical", _obj({}),
         _call("imedical", "GET", "/imedical/api/v2/especialidades")),
    Tool("consultar_disponibilidad",
         "iMedical. Cupos DISPONIBLES en agenda para una especialidad (ordenados por fecha). Devuelve id_slot, "
         "fecha, hora, profesional, sede y la primera fecha disponible.",
         "iMedical", _obj({
             "especialidad": {"type": S, "description": "Ej: 'Medicina Interna', 'Pediatria', 'Toma de muestras'"},
             "sede": {"type": S, "description": "Opcional: 'Centro', 'Norte', 'Duitama'"},
             "fecha_desde": {"type": S, "description": "Opcional AAAA-MM-DD"},
             "fecha_hasta": {"type": S, "description": "Opcional AAAA-MM-DD"},
             "jornada": {"type": S, "description": "Opcional: 'manana' o 'tarde'"},
             "limite": {"type": I, "description": "Cantidad de cupos a devolver (por defecto 5)"},
         }, ["especialidad"]),
         _call("imedical", "GET", "/imedical/api/v2/agenda/disponibilidad",
               lambda a: {"especialidad": a["especialidad"], "sede": a.get("sede"), "fecha_desde": a.get("fecha_desde"),
                          "fecha_hasta": a.get("fecha_hasta"), "jornada": a.get("jornada"), "limite": a.get("limite", 5)})),
    Tool("consultar_citas_paciente",
         "iMedical. Citas del paciente (pasadas y futuras) con estado: ASIGNADA, CONFIRMADA, CUMPLIDA, CANCELADA, "
         "INASISTENCIA.",
         "iMedical", _obj({"numero_documento": DOC,
                           "solo_futuras": {"type": B, "description": "true para ver solo citas pendientes"}},
                          ["numero_documento"]),
         _call("imedical", "GET", "/imedical/api/v2/citas",
               lambda a: {**_doc(a), "solo_futuras": str(a.get("solo_futuras", False)).lower()})),
    Tool("consultar_historia_resumen",
         "iMedical. Resumen clinico basico: telefono de contacto registrado en iMedical, grupo sanguineo, alergias, "
         "antecedentes (CIE-10) y ultima atencion.",
         "iMedical", _obj({"numero_documento": DOC}, ["numero_documento"]),
         _call("imedical", "GET", "/imedical/api/v2/pacientes/{numero_documento}/historia-resumen")),
    Tool("agendar_cita",
         "iMedical. ASIGNA una cita en un cupo (id_slot). SOLO usar despues de que el agente confirme explicitamente. "
         "Valida afiliacion, autorizacion vigente y restricciones de edad/sexo.",
         "iMedical", _obj({
             "numero_documento": DOC,
             "id_slot": {"type": S, "description": "id_slot devuelto por consultar_disponibilidad"},
             "canal_origen": {"type": S, "description": "Llamada, WhatsApp o Web"},
             "atencion_particular": {"type": B, "description": "true si el paciente pagara como particular"},
             "observaciones": {"type": S},
         }, ["numero_documento", "id_slot"]),
         _call("imedical", "POST", "/imedical/api/v2/citas",
               body_fn=lambda a: {**_doc(a), "id_slot": a["id_slot"],
                                  "canal_origen": a.get("canal_origen") or "Copiloto call center",
                                  "atencion_particular": bool(a.get("atencion_particular", False)),
                                  "observaciones": a.get("observaciones")})),
    Tool("liberar_cupo",
         "iMedical. CANCELA una cita médica o LIBERA un cupo de agenda usando el código del cupo (id_slot, ej: 'AG-000255') "
         "o el número de documento/cédula del paciente (ej: '1049632145') o el radicado de la cita (ej: 'CIT-980952'). "
         "Marca la cita como CANCELADA y el cupo en agenda vuelve a quedar DISPONIBLE.",
         "iMedical", _obj({
             "id_slot": {"type": S, "description": "Código del cupo a liberar (ej: 'AG-000255')"},
             "numero_documento": {"type": S, "description": "Cédula o documento del paciente"},
             "id_cita": {"type": S, "description": "Código radicado de la cita (ej: 'CIT-980952')"},
             "motivo": {"type": S, "description": "Motivo opcional de cancelación"}
         }),
         _call("imedical", "POST", "/imedical/api/v2/agenda/liberar",
               body_fn=lambda a: {
                   "id_slot": a.get("id_slot"),
                   "numero_documento": solo_digitos(a["numero_documento"]) if a.get("numero_documento") else None,
                   "id_cita": a.get("id_cita"),
                   "motivo": a.get("motivo") or "Solicitud de cancelación / liberación de cupo"
               })),
    Tool("cancelar_cita",
         "iMedical. Alias de liberar_cupo. Cancela la cita médica y libera el cupo de agenda.",
         "iMedical", _obj({
             "id_slot": {"type": S, "description": "Código del cupo a liberar (ej: 'AG-000255')"},
             "numero_documento": {"type": S, "description": "Cédula o documento del paciente"},
             "id_cita": {"type": S, "description": "Código de la cita (ej: 'CIT-980952')"},
             "motivo": {"type": S, "description": "Motivo de cancelación"}
         }),
         _call("imedical", "POST", "/imedical/api/v2/agenda/liberar",
               body_fn=lambda a: {
                   "id_slot": a.get("id_slot"),
                   "numero_documento": solo_digitos(a["numero_documento"]) if a.get("numero_documento") else None,
                   "id_cita": a.get("id_cita"),
                   "motivo": a.get("motivo") or "Solicitud de cancelación / liberación de cupo"
               })),
    # ------------------------------ SAGICC ------------------------------
    Tool("historial_interacciones",
         "SAGICC. Ultimas interacciones del usuario con el contact center (llamadas, WhatsApp, web): canal, fecha, "
         "tiempo de espera, tipificacion, resultado y resumen.",
         "SAGICC", _obj({"numero_documento": DOC, "limite": {"type": I}}, ["numero_documento"]),
         _call("sagicc", "GET", "/sagicc/api/v1/interacciones", lambda a: {**_doc(a), "limite": a.get("limite", 5)})),
    Tool("consultar_pqrs",
         "SAGICC. PQRS radicadas por el usuario: tipo, motivo, estado, fecha limite de respuesta y si esta vencida.",
         "SAGICC", _obj({"numero_documento": DOC}, ["numero_documento"]),
         _call("sagicc", "GET", "/sagicc/api/v1/pqrs", _doc)),
    Tool("metricas_contact_center",
         "SAGICC. Indicadores del contact center: espera promedio, AHT, abandono, tiempo consultando sistemas, "
         "top tipificaciones y PQRS abiertas/vencidas.",
         "SAGICC", _obj({"dias": {"type": I, "description": "Periodo en dias (1-30, por defecto 7)"}}),
         _call("sagicc", "GET", "/sagicc/api/v1/metricas", lambda a: {"dias": a.get("dias", 7)})),
    # ------------------------------ RAG ------------------------------
    Tool("buscar_documentacion",
         "Base documental (RAG). Protocolos de preparacion de examenes, horarios y sedes, portafolio, requisitos "
         "por EPS, politica de cancelacion e inasistencia, entrega de resultados, PQRS, toma de muestras a domicilio.",
         "Base documental", _obj({"pregunta": {"type": S, "description": "Pregunta en lenguaje natural"}}, ["pregunta"]),
         _rag),
]

TOOLS_BY_NAME = {t.name: t for t in TOOLS}
MAX_CHARS_RESULTADO = 12000


def declaraciones_gemini() -> list[dict]:
    return [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in TOOLS]


async def ejecutar_tool(api: ApiClient, nombre: str, args: dict) -> tuple[dict, dict]:
    """Ejecuta una tool y devuelve (resultado_para_el_llm, traza_para_la_ui)."""
    tool = TOOLS_BY_NAME.get(nombre)
    if not tool:
        return {"error": f"Herramienta desconocida: {nombre}"}, {"tool": nombre, "sistema": "?", "status": 400}
    try:
        status, data, info = await tool.run(api, args)
    except KeyError as exc:
        status, data, info = 400, {"detail": f"Falta el parametro {exc}"}, {}
    traza = {"tool": nombre, "sistema": tool.sistema, "status": status, "args": args, **info}
    if status >= 400:
        resultado = {"error": True, "status": status, "detalle": data.get("detail") if isinstance(data, dict) else data}
    else:
        resultado = data
    texto = json.dumps(resultado, ensure_ascii=False, default=str)
    if len(texto) > MAX_CHARS_RESULTADO:
        resultado = {"aviso": "Resultado truncado", "contenido_parcial": texto[:MAX_CHARS_RESULTADO]}
    return resultado, traza


async def ejecutar_varias(api: ApiClient, llamadas: list[tuple[str, dict]]) -> list[tuple[dict, dict]]:
    return await asyncio.gather(*(ejecutar_tool(api, n, a) for n, a in llamadas))
