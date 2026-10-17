"""
API simulada de ATHENEA (gestion administrativa/asistencial + LABORATORIO).

Formato de respuesta estilo Athenea: {"status": "ok", "data": ..., "total": n}
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import hoy
from app.data_store import get_store, normalizar, solo_digitos
from app.mocks.common import edad, require_api_key

router = APIRouter(prefix="/athenea/api/v1", tags=["Athenea"], dependencies=[require_api_key("athenea")])


class PacienteCrear(BaseModel):
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
    departamento: str | None = "Boyaca"
    eps: str | None = "Particular"
    empresa: str | None = None
    acepta_whatsapp: bool = True


class PacienteActualizar(BaseModel):
    telefono: str | None = None
    email: str | None = None
    direccion: str | None = None
    municipio: str | None = None
    eps: str | None = None
    empresa: str | None = None
    acepta_whatsapp: bool | None = None


def ok(data, **extra):
    total = len(data) if isinstance(data, list) else 1
    return {"status": "ok", "sistema": "Athenea", "data": data, "total": total, **extra}


def _estado_autorizacion(a: dict) -> str:
    if a["estado"] == "VIGENTE" and a["fecha_vencimiento"] < hoy().isoformat():
        return "VENCIDA"
    return a["estado"]


@router.get("/pacientes/{numero_documento}", summary="Consultar paciente por documento")
def obtener_paciente(numero_documento: str):
    p = get_store().paciente(numero_documento)
    if not p:
        raise HTTPException(404, detail=f"Paciente con documento {solo_digitos(numero_documento)} no existe en Athenea")
    return ok({**p, "edad": edad(p["fecha_nacimiento"])})


@router.post("/pacientes", status_code=status.HTTP_201_CREATED, summary="Registrar nuevo paciente en Athenea")
def registrar_paciente(body: PacienteCrear):
    store = get_store()
    doc = solo_digitos(body.numero_documento)
    if store.paciente(doc):
        raise HTTPException(status_code=400, detail=f"El paciente con documento {doc} ya se encuentra registrado en Athenea")

    nombres = [body.primer_nombre, body.segundo_nombre, body.primer_apellido, body.segundo_apellido]
    nombre_completo = " ".join([n for n in nombres if n]).strip()

    paciente_dict = {
        "id_paciente": f"ATH-PAC-{len(store.pacientes) + 1:06d}",
        "tipo_documento": body.tipo_documento.upper(),
        "numero_documento": doc,
        "primer_nombre": body.primer_nombre,
        "segundo_nombre": body.segundo_nombre,
        "primer_apellido": body.primer_apellido,
        "segundo_apellido": body.segundo_apellido,
        "nombre_completo": nombre_completo,
        "fecha_nacimiento": body.fecha_nacimiento,
        "sexo": (body.sexo or "M").upper(),
        "telefono": body.telefono,
        "email": body.email,
        "direccion": body.direccion,
        "municipio": body.municipio or "Tunja",
        "departamento": body.departamento or "Boyaca",
        "afiliacion": {
            "eps": body.eps or "Particular",
            "regimen": "Contributivo" if body.eps and body.eps.lower() != "particular" else "Particular",
            "tipo_afiliado": "Cotizante",
            "categoria": "A",
            "estado": "ACTIVO",
            "fecha_ultima_validacion": hoy().isoformat(),
        },
        "empresa": body.empresa,
        "acepta_whatsapp": body.acepta_whatsapp,
    }
    nuevo = store.guardar_paciente(paciente_dict)
    return ok({**nuevo, "edad": edad(nuevo["fecha_nacimiento"])}, mensaje="Paciente registrado exitosamente")


@router.patch("/pacientes/{numero_documento}", summary="Actualizar datos demográficos/contacto de paciente")
def actualizar_datos_paciente(numero_documento: str, body: PacienteActualizar):
    store = get_store()
    doc = solo_digitos(numero_documento)
    if not store.paciente(doc):
        raise HTTPException(status_code=404, detail=f"Paciente con documento {doc} no existe en Athenea")

    campos = body.dict(exclude_unset=True)
    actualizado = store.actualizar_paciente(doc, campos)
    return ok({**actualizado, "edad": edad(actualizado["fecha_nacimiento"])}, mensaje="Datos de paciente actualizados exitosamente")


@router.get("/pacientes", summary="Buscar pacientes por nombre")
def buscar_pacientes(nombre: str = Query(..., min_length=3), limite: int = Query(10, ge=1, le=50)):
    tokens = normalizar(nombre).split()
    encontrados = [
        {"numero_documento": p["numero_documento"], "tipo_documento": p["tipo_documento"],
         "nombre_completo": p["nombre_completo"], "edad": edad(p["fecha_nacimiento"]), "municipio": p["municipio"],
         "eps": p["afiliacion"]["eps"]}
        for p in get_store().athenea["pacientes"]
        if all(t in normalizar(p["nombre_completo"]) for t in tokens)
    ]
    return ok(encontrados[:limite])


@router.get("/autorizaciones", summary="Autorizaciones de servicios de un paciente")
def autorizaciones(numero_documento: str, estado: str | None = None):
    data = [{**a, "estado": _estado_autorizacion(a)} for a in get_store().por_documento("autorizaciones", numero_documento)]
    if estado:
        data = [a for a in data if a["estado"] == estado.upper()]
    return ok(sorted(data, key=lambda a: a["fecha_emision"], reverse=True))


@router.get("/tarifas", summary="Tarifas por servicio y entidad")
def tarifas(servicio: str | None = None, entidad: str | None = None, limite: int = Query(20, ge=1, le=100)):
    data = get_store().athenea["tarifas"]
    if servicio:
        tokens = normalizar(servicio).split()
        data = [t for t in data if all(tok in normalizar(t["servicio"]) + " " + t["codigo_cups"] for tok in tokens)]
    if entidad:
        data = [t for t in data if normalizar(entidad) in normalizar(t["entidad"])]
    return ok(data[:limite])


@router.get("/cuotas-moderadoras", summary="Cuotas moderadoras y copagos vigentes")
def cuotas_moderadoras():
    return ok(get_store().athenea["cuotas_moderadoras"])


# ---------------------------- Laboratorio ----------------------------
@router.get("/laboratorio/examenes", summary="Catalogo de examenes de laboratorio")
def examenes(nombre: str | None = None):
    data = get_store().athenea["examenes_laboratorio"]
    if nombre:
        data = [e for e in data if normalizar(nombre) in normalizar(e["examen"])]
    return ok(data)


@router.get("/laboratorio/resultados", summary="Ordenes de laboratorio y estado de resultados")
def resultados(numero_documento: str):
    store = get_store()
    if not store.paciente(numero_documento):
        raise HTTPException(404, detail="Paciente no existe en Athenea")
    data = sorted(store.por_documento("resultados", numero_documento), key=lambda r: r["fecha_toma"], reverse=True)
    return ok(data, nota="Por confidencialidad la API del MVP solo expone el estado, no los valores clinicos.")
