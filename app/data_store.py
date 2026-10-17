"""
Almacen en memoria con los datos sinteticos de Athenea, iMedical y SAGICC.

- Carga los JSON generados por data/generate_data.py.
- Desplaza todas las fechas en semanas completas para que la agenda quede "vigente"
  respecto a la fecha actual (se conserva el dia de la semana).
- Mantiene indices por numero de documento.

Nota: las escrituras (agendar/cancelar) viven en memoria del proceso. En Vercel
(serverless) se reinician en cada arranque en frio; suficiente para un MVP.
"""
from __future__ import annotations

import json
import threading
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache

from app.config import DATA_DIR, hoy

CAMPOS_SIN_DESPLAZAR = {"fecha_nacimiento"}


def normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip()


def solo_digitos(doc: str) -> str:
    limpio = "".join(c for c in str(doc) if c.isalnum())
    return limpio.upper() if not limpio.isdigit() else limpio


def _desplazar(valor: str, delta: timedelta) -> str:
    try:
        if "T" in valor:
            return (datetime.fromisoformat(valor) + delta).isoformat(timespec="seconds")
        return (date.fromisoformat(valor) + delta).isoformat()
    except ValueError:
        return valor


def _desplazar_registro(obj, delta: timedelta):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and (k.startswith("fecha") or k == "ultima_atencion") and k not in CAMPOS_SIN_DESPLAZAR:
                obj[k] = _desplazar(v, delta)
            elif isinstance(v, (dict, list)):
                _desplazar_registro(v, delta)
    elif isinstance(obj, list):
        for item in obj:
            _desplazar_registro(item, delta)


class DataStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.athenea = json.loads((DATA_DIR / "athenea.json").read_text(encoding="utf-8"))
        self.imedical = json.loads((DATA_DIR / "imedical.json").read_text(encoding="utf-8"))
        self.sagicc = json.loads((DATA_DIR / "sagicc.json").read_text(encoding="utf-8"))

        ancla = date.fromisoformat(self.athenea["meta"]["fecha_ancla"])
        semanas = (hoy() - ancla).days // 7
        self.delta = timedelta(weeks=semanas)
        if semanas:
            for fuente in (self.athenea, self.imedical, self.sagicc):
                for clave, valor in fuente.items():
                    if clave != "meta":
                        _desplazar_registro(valor, self.delta)

        self.pacientes = {p["numero_documento"]: p for p in self.athenea["pacientes"]}
        self.historias = {h["numero_documento"]: h for h in self.imedical["historias"]}
        self.slots = {s["id_slot"]: s for s in self.imedical["agenda"]}
        self._idx_citas: dict[str, list] = defaultdict(list)
        for c in self.imedical["citas"]:
            self._idx_citas[c["numero_documento"]].append(c)
        self._idx = {
            "autorizaciones": self._indexar(self.athenea["autorizaciones"]),
            "resultados": self._indexar(self.athenea["resultados"]),
            "interacciones": self._indexar(self.sagicc["interacciones"]),
            "pqrs": self._indexar(self.sagicc["pqrs"]),
        }
        self._seq_cita = len(self.imedical["citas"])

    @staticmethod
    def _indexar(registros: list[dict]) -> dict[str, list[dict]]:
        idx: dict[str, list[dict]] = defaultdict(list)
        for r in registros:
            idx[r["numero_documento"]].append(r)
        return idx

    # ---- consultas ----
    def paciente(self, doc: str) -> dict | None:
        return self.pacientes.get(solo_digitos(doc))

    def por_documento(self, coleccion: str, doc: str) -> list[dict]:
        if coleccion == "citas":
            return list(self._idx_citas.get(solo_digitos(doc), []))
        return list(self._idx[coleccion].get(solo_digitos(doc), []))

    # ---- escrituras (en memoria) ----
    def registrar_cita(self, cita: dict) -> dict:
        self._seq_cita += 1
        cita["id_cita"] = f"CIT-{self._seq_cita:06d}"
        self.imedical["citas"].append(cita)
        self._idx_citas[cita["numero_documento"]].append(cita)
        return cita

    def guardar_paciente(self, paciente: dict) -> dict:
        with self.lock:
            doc = solo_digitos(paciente["numero_documento"])
            if not paciente.get("id_paciente"):
                paciente["id_paciente"] = f"ATH-PAC-{len(self.pacientes) + 1:06d}"
            self.pacientes[doc] = paciente
            self.athenea["pacientes"].append(paciente)
            return paciente

    def actualizar_paciente(self, doc: str, campos: dict) -> dict | None:
        with self.lock:
            p = self.paciente(doc)
            if not p:
                return None
            for k, v in campos.items():
                if v is not None:
                    if k == "afiliacion" and isinstance(v, dict) and isinstance(p.get("afiliacion"), dict):
                        p["afiliacion"].update(v)
                    elif k == "eps":
                        if "afiliacion" not in p or not isinstance(p["afiliacion"], dict):
                            p["afiliacion"] = {}
                        p["afiliacion"]["eps"] = v
                    else:
                        p[k] = v
            if any(k in campos for k in ("primer_nombre", "segundo_nombre", "primer_apellido", "segundo_apellido")):
                nombres = [p.get("primer_nombre"), p.get("segundo_nombre"), p.get("primer_apellido"), p.get("segundo_apellido")]
                p["nombre_completo"] = " ".join([n for n in nombres if n]).strip()
            return p


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    return DataStore()
