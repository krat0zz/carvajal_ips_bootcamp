"""
API simulada de iMEDICAL (HIS: agendas, citas, turnos y resumen de historia clinica).

Formato de respuesta estilo iMedical: {"resultado": ..., "total": n, "codigo": 200}
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import ahora
from app.data_store import get_store, normalizar, solo_digitos
from app.mocks.common import edad, require_api_key

router = APIRouter(prefix="/imedical/api/v2", tags=["iMedical"], dependencies=[require_api_key("imedical")])

ESTADOS_ACTIVOS = {"ASIGNADA", "CONFIRMADA"}


def ok(resultado, **extra):
    total = len(resultado) if isinstance(resultado, list) else 1
    return {"codigo": 200, "sistema": "iMedical", "resultado": resultado, "total": total, **extra}


def _resolver_especialidad(texto: str) -> dict:
    especialidades = get_store().imedical["especialidades"]
    t = normalizar(texto)
    for e in especialidades:
        if t == normalizar(e["especialidad"]):
            return e
    candidatas = [e for e in especialidades if t in normalizar(e["especialidad"]) or normalizar(e["especialidad"]) in t]
    if not candidatas:
        tokens = t.split()
        candidatas = [e for e in especialidades if any(tok in normalizar(e["especialidad"]) for tok in tokens if len(tok) > 3)]
    if not candidatas:
        raise HTTPException(404, detail={"mensaje": f"Especialidad '{texto}' no encontrada",
                                         "especialidades_validas": [e["especialidad"] for e in especialidades]})
    return candidatas[0]


def _es_futuro(fecha: str, hora: str) -> bool:
    now = ahora()
    return (fecha, hora) > (now.date().isoformat(), now.strftime("%H:%M"))


@router.get("/especialidades", summary="Especialidades, sedes y reglas de agendamiento")
def especialidades():
    return ok(get_store().imedical["especialidades"])


@router.get("/sedes", summary="Sedes de atencion")
def sedes():
    return ok(get_store().imedical["sedes"])


@router.get("/profesionales", summary="Profesionales por especialidad")
def profesionales(especialidad: str | None = None):
    data = get_store().imedical["profesionales"]
    if especialidad:
        esp = _resolver_especialidad(especialidad)["especialidad"]
        data = [p for p in data if p["especialidad"] == esp]
    return ok(data)


@router.get("/agenda/disponibilidad", summary="Cupos disponibles en agenda")
def disponibilidad(
    especialidad: str,
    sede: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    jornada: str | None = Query(None, description="manana | tarde"),
    limite: int = Query(8, ge=1, le=50),
):
    esp = _resolver_especialidad(especialidad)
    slots = [s for s in get_store().imedical["agenda"]
             if s["especialidad"] == esp["especialidad"] and s["estado"] == "DISPONIBLE" and _es_futuro(s["fecha"], s["hora"])]
    if sede:
        slots = [s for s in slots if normalizar(sede) in normalizar(s["sede"])]
    if fecha_desde:
        slots = [s for s in slots if s["fecha"] >= fecha_desde.isoformat()]
    if fecha_hasta:
        slots = [s for s in slots if s["fecha"] <= fecha_hasta.isoformat()]
    if jornada:
        j = normalizar(jornada)
        slots = [s for s in slots if (s["hora"] < "12:00") == j.startswith("man")]
    slots.sort(key=lambda s: (s["fecha"], s["hora"]))
    campos = ("id_slot", "fecha", "hora", "duracion_min", "profesional", "sede")
    return ok(
        [{k: s[k] for k in campos} for s in slots[:limite]],
        especialidad=esp["especialidad"],
        requiere_autorizacion=esp["requiere_autorizacion"],
        total_cupos_disponibles=len(slots),
        primera_fecha_disponible=slots[0]["fecha"] if slots else None,
    )


@router.get("/citas", summary="Citas de un paciente")
def citas(numero_documento: str, estado: str | None = None, solo_futuras: bool = False):
    data = get_store().por_documento("citas", numero_documento)
    if estado:
        data = [c for c in data if c["estado"] == estado.upper()]
    if solo_futuras:
        data = [c for c in data if c["fecha_hora"][:16] > ahora().strftime("%Y-%m-%dT%H:%M")]
    return ok(sorted(data, key=lambda c: c["fecha_hora"], reverse=True))


@router.get("/pacientes/{numero_documento}/historia-resumen", summary="Resumen basico de historia clinica")
def historia_resumen(numero_documento: str):
    h = get_store().historias.get(solo_digitos(numero_documento))
    if not h:
        raise HTTPException(404, detail="Paciente sin historia clinica en iMedical")
    return ok(h)


class NuevaCita(BaseModel):
    numero_documento: str
    id_slot: str
    canal_origen: str = Field("Copiloto call center", description="Llamada, WhatsApp, Web, Copiloto call center")
    numero_autorizacion: str | None = None
    atencion_particular: bool = Field(False, description="True si el paciente pagara como particular")
    observaciones: str | None = None


@router.post("/citas", status_code=201, summary="Asignar cita en un cupo disponible")
def crear_cita(body: NuevaCita):
    store = get_store()
    with store.lock:
        paciente = store.paciente(body.numero_documento)
        if not paciente:
            raise HTTPException(404, detail="Paciente no registrado")
        slot = store.slots.get(body.id_slot)
        if not slot:
            raise HTTPException(404, detail=f"Cupo {body.id_slot} no existe")
        if slot["estado"] != "DISPONIBLE" or not _es_futuro(slot["fecha"], slot["hora"]):
            raise HTTPException(409, detail=f"El cupo {body.id_slot} ya no esta disponible")
        esp = _resolver_especialidad(slot["especialidad"])

        e = edad(paciente["fecha_nacimiento"])
        if not (esp["restriccion_edad"]["min"] <= e <= esp["restriccion_edad"]["max"]):
            raise HTTPException(422, detail=f"{esp['especialidad']} no atiende pacientes de {e} anos")
        if esp["restriccion_sexo"] and esp["restriccion_sexo"] != paciente["sexo"]:
            raise HTTPException(422, detail=f"{esp['especialidad']} no aplica para el sexo del paciente")

        afil = paciente["afiliacion"]
        particular = body.atencion_particular or afil["regimen"] == "Particular"
        if not particular:
            if afil["estado"] in ("SUSPENDIDO", "RETIRADO"):
                raise HTTPException(409, detail=f"Afiliacion {afil['estado']} en {afil['eps']}. "
                                                "Solo puede agendarse como atencion particular.")
            if esp["requiere_autorizacion"]:
                vigentes = [a for a in store.por_documento("autorizaciones", body.numero_documento)
                            if a["estado"] == "VIGENTE" and a["especialidad"] == esp["especialidad"]
                            and a["fecha_vencimiento"] >= slot["fecha"]]
                if body.numero_autorizacion:
                    vigentes = [a for a in vigentes if a["numero_autorizacion"] == body.numero_autorizacion]
                if not vigentes:
                    raise HTTPException(422, detail=f"{esp['especialidad']} requiere autorizacion VIGENTE de la EPS "
                                                    "a la fecha de la cita")
                body.numero_autorizacion = vigentes[0]["numero_autorizacion"]

        cita = store.registrar_cita({
            "numero_documento": paciente["numero_documento"],
            "paciente": paciente["nombre_completo"],
            "id_profesional": slot["id_profesional"],
            "profesional": slot["profesional"],
            "especialidad": slot["especialidad"],
            "sede": slot["sede"],
            "fecha_hora": f"{slot['fecha']}T{slot['hora']}:00",
            "estado": "ASIGNADA",
            "canal_origen": body.canal_origen,
            "numero_autorizacion": None if particular else body.numero_autorizacion,
            "id_slot": slot["id_slot"],
            "atencion_particular": particular,
            "observaciones": body.observaciones,
        })
        slot["estado"], slot["id_cita"] = "OCUPADO", cita["id_cita"]
    return ok(cita, mensaje="Cita asignada correctamente")


class SolicitudLiberarCupo(BaseModel):
    id_slot: str | None = None
    numero_documento: str | None = None
    id_cita: str | None = None
    motivo: str = "Solicitud del paciente"


@router.post("/agenda/liberar", summary="Liberar cupo o cancelar cita por AG o CC")
def liberar_cupo_endpoint(body: SolicitudLiberarCupo):
    store = get_store()
    with store.lock:
        cita_encontrada = None
        slot_a_liberar = None

        # 1. Por código de cupo AG-
        if body.id_slot:
            slot_id = body.id_slot.upper()
            slot_a_liberar = store.slots.get(slot_id)
            if not slot_a_liberar:
                raise HTTPException(404, detail=f"Cupo {body.id_slot} no existe en la agenda de iMedical")
            cita_encontrada = next((c for c in store.imedical["citas"] if c.get("id_slot") == slot_id and c["estado"] in ESTADOS_ACTIVOS), None)

        # 2. Por código de cita CIT-
        elif body.id_cita:
            cita_encontrada = next((c for c in store.imedical["citas"] if c["id_cita"] == body.id_cita.upper()), None)
            if not cita_encontrada:
                raise HTTPException(404, detail=f"Cita {body.id_cita} no encontrada")
            slot_a_liberar = store.slots.get(cita_encontrada.get("id_slot") or "")

        # 3. Por número de documento del paciente
        elif body.numero_documento:
            doc = solo_digitos(body.numero_documento)
            citas_pac = [c for c in store.por_documento("citas", doc) if c["estado"] in ESTADOS_ACTIVOS]
            if not citas_pac:
                raise HTTPException(404, detail=f"El paciente con documento {doc} no tiene citas activas pendientes para cancelar en iMedical")
            cita_encontrada = citas_pac[0]
            slot_a_liberar = store.slots.get(cita_encontrada.get("id_slot") or "")

        else:
            raise HTTPException(400, detail="Debes especificar al menos el código del cupo (id_slot, ej: AG-000255) o el número de documento del paciente.")

        if slot_a_liberar:
            slot_a_liberar["estado"] = "DISPONIBLE"
            slot_a_liberar["id_cita"] = None

        if cita_encontrada:
            cita_encontrada["estado"] = "CANCELADA"
            cita_encontrada["motivo_cancelacion"] = body.motivo

        return ok({
            "id_slot": slot_a_liberar["id_slot"] if slot_a_liberar else None,
            "id_cita": cita_encontrada["id_cita"] if cita_encontrada else None,
            "paciente": cita_encontrada["paciente"] if cita_encontrada else None,
            "especialidad": cita_encontrada["especialidad"] if cita_encontrada else None,
            "fecha_hora": cita_encontrada["fecha_hora"] if cita_encontrada else None,
            "estado_cupo": "DISPONIBLE",
            "estado_cita": "CANCELADA" if cita_encontrada else None,
            "motivo": body.motivo
        }, mensaje="Cupo liberado exitosamente y cita cancelada")


class Cancelacion(BaseModel):
    motivo: str = "Solicitud del paciente"


@router.post("/citas/{id_cita}/cancelar", summary="Cancelar una cita y liberar el cupo")
def cancelar_cita(id_cita: str, body: Cancelacion):
    return liberar_cupo_endpoint(SolicitudLiberarCupo(id_cita=id_cita, motivo=body.motivo))
