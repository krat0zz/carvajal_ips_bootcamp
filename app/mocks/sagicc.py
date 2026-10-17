"""
API simulada de SAGICC (contact center omnicanal: voz, WhatsApp, web chat, PQRS).

Formato de respuesta estilo SAGICC: {"success": true, "data": [...], "count": n}
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from fastapi import APIRouter, Query

from app.config import ahora, hoy
from app.data_store import get_store
from app.mocks.common import require_api_key

router = APIRouter(prefix="/sagicc/api/v1", tags=["SAGICC"], dependencies=[require_api_key("sagicc")])


def ok(data, **extra):
    return {"success": True, "sistema": "SAGICC", "data": data,
            "count": len(data) if isinstance(data, list) else 1, **extra}


@router.get("/interacciones", summary="Historial de interacciones de un usuario")
def interacciones(numero_documento: str, limite: int = Query(10, ge=1, le=50)):
    data = sorted(get_store().por_documento("interacciones", numero_documento),
                  key=lambda i: i["fecha_inicio"], reverse=True)
    return ok(data[:limite], total_historico=len(data))


@router.get("/pqrs", summary="PQRS de un usuario")
def pqrs(numero_documento: str, estado: str | None = None):
    data = get_store().por_documento("pqrs", numero_documento)
    if estado:
        data = [p for p in data if p["estado"] == estado.upper()]
    hoy_iso = hoy().isoformat()
    for p in data:
        p["vencida"] = p["estado"] in ("RADICADA", "EN_GESTION") and p["fecha_limite_respuesta"] < hoy_iso
    return ok(sorted(data, key=lambda p: p["fecha_radicacion"], reverse=True))


@router.get("/agentes", summary="Agentes del contact center")
def agentes():
    return ok(get_store().sagicc["agentes"])


@router.get("/metricas", summary="Indicadores del contact center")
def metricas(dias: int = Query(7, ge=1, le=30)):
    store = get_store()
    desde = (ahora() - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S")
    datos = [i for i in store.sagicc["interacciones"] if i["fecha_inicio"] >= desde]
    por_canal: dict[str, list] = defaultdict(list)
    for i in datos:
        por_canal[i["canal"]].append(i)

    def resumen(items: list[dict]) -> dict:
        atendidas = [i for i in items if i["resultado"] != "ABANDONADO"]
        n_at = max(1, len(atendidas))
        aht = sum(i["duracion_seg"] for i in atendidas) / n_at
        consulta = sum(i["tiempo_consulta_sistemas_seg"] for i in atendidas) / n_at
        return {
            "total": len(items),
            "atendidas": len(atendidas),
            "tasa_abandono_pct": round(100 * (len(items) - len(atendidas)) / max(1, len(items)), 1),
            "espera_promedio_min": round(sum(i["tiempo_espera_seg"] for i in items) / max(1, len(items)) / 60, 1),
            "aht_promedio_min": round(aht / 60, 1),
            "tiempo_consulta_sistemas_promedio_min": round(consulta / 60, 1),
            "pct_aht_en_consulta_sistemas": round(100 * consulta / aht, 1) if aht else 0,
            "resueltas_primer_contacto_pct": round(100 * sum(i["resultado"] == "RESUELTO" for i in items) / max(1, len(items)), 1),
        }

    pqrs = store.sagicc["pqrs"]
    hoy_iso = hoy().isoformat()
    abiertas = [p for p in pqrs if p["estado"] in ("RADICADA", "EN_GESTION")]
    return ok({
        "periodo_dias": dias,
        "global": resumen(datos),
        "por_canal": {c: resumen(v) for c, v in por_canal.items()},
        "top_tipificaciones": Counter(i["tipificacion"] for i in datos).most_common(5),
        "pqrs": {
            "abiertas": len(abiertas),
            "vencidas": sum(p["fecha_limite_respuesta"] < hoy_iso for p in abiertas),
            "top_motivos": Counter(p["motivo"] for p in pqrs).most_common(5),
        },
    })
