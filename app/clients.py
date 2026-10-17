"""
Cliente HTTP que ejecuta las consultas GET a la API REST de Supabase (o a los mocks locales).
Cada función traduce los argumentos del modelo de IA a un GET con filtros PostgREST y API Key.
"""
from __future__ import annotations

import time
from typing import Any
import httpx
from app.config import hoy, settings

class ApiClient:
    def __init__(self) -> None:
        self.usa_supabase = bool(settings.mock_base_url.startswith("http") or os_supabase_configured())
        
        if os_supabase_configured():
            # Conexión directa a la API REST oficial de Supabase
            import os
            base = os.getenv("SUPABASE_URL", "").rstrip("/").removesuffix("/rest/v1")
            url = base + "/rest/v1"
            key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            self._client = httpx.AsyncClient(base_url=url, headers=headers, timeout=15.0)
            self.modo = "SUPABASE_REST_API"
        else:
            # Fallback a endpoints FastAPI locales en memoria
            from app.mocks import mock_app
            self._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app),
                                             base_url="http://mock.internal", timeout=15.0)
            self.modo = "LOCAL_MOCK_API"

    async def __aenter__(self) -> "ApiClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def get_supabase(self, tabla: str, params: dict | None = None) -> tuple[int, Any, float]:
        """Realiza una petición HTTP GET con API Key a una tabla de Supabase."""
        t0 = time.perf_counter()
        try:
            resp = await self._client.get(f"/{tabla}", params=params)
            ms = (time.perf_counter() - t0) * 1000
            try:
                data = resp.json()
            except ValueError:
                data = {"raw": resp.text}
            return resp.status_code, data, ms
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000
            return 500, {"error": str(exc)}, ms

    async def request(self, sistema: str, metodo: str, ruta: str, params: dict | None = None,
                      json: dict | None = None) -> tuple[int, Any, float]:
        """Interfaz universal compatible con local y Supabase."""
        if self.modo == "SUPABASE_REST_API":
            return await self._traducir_a_supabase(sistema, metodo, ruta, params, json)

        # Modo Local con Header x-api-key
        headers = {"x-api-key": getattr(settings, f"{sistema}_api_key")}
        t0 = time.perf_counter()
        try:
            resp = await self._client.request(metodo, ruta, params=params, json=json, headers=headers)
            ms = (time.perf_counter() - t0) * 1000
            return resp.status_code, resp.json(), ms
        except Exception as exc:
            return 500, {"error": str(exc)}, (time.perf_counter() - t0) * 1000

    async def _traducir_a_supabase(self, sistema: str, metodo: str, ruta: str, params: dict | None, json_body: dict | None):
        """Traduce las llamadas del copiloto a endpoints GET de tablas Supabase."""
        params = params or {}
        t0 = time.perf_counter()

        # 1. ATHENEA: Pacientes
        if "pacientes" in ruta:
            if metodo == "GET":
                doc = ruta.split("/")[-1] if not params.get("nombre") else None
                if doc and doc != "pacientes":
                    st, data, ms = await self.get_supabase("athenea_pacientes", {"numero_documento": f"eq.{doc}"})
                    res = data[0] if isinstance(data, list) and len(data) > 0 else None
                    return (200, {"status": "ok", "data": res}, ms) if res else (404, {"detail": "Paciente no existe"}, ms)
                elif params.get("nombre"):
                    st, data, ms = await self.get_supabase("athenea_pacientes", {"nombre_completo": f"ilike.*{params['nombre']}*"})
                    return st, {"status": "ok", "data": data}, ms
            elif metodo == "POST":
                # Registro de nuevo paciente en Supabase
                body = json_body or {}
                doc = str(body.get("numero_documento", ""))
                st_ex, data_ex, _ = await self.get_supabase("athenea_pacientes", {"numero_documento": f"eq.{doc}"})
                if data_ex and len(data_ex) > 0:
                    return 400, {"detail": f"El paciente con documento {doc} ya se encuentra registrado"}, 0

                import random
                id_pac = body.get("id_paciente") or f"ATH-PAC-{random.randint(100000, 999999)}"
                nombres = [body.get("primer_nombre"), body.get("segundo_nombre"), body.get("primer_apellido"), body.get("segundo_apellido")]
                nombre_comp = body.get("nombre_completo") or " ".join([n for n in nombres if n]).strip()

                registro = {
                    "id_paciente": id_pac,
                    "tipo_documento": (body.get("tipo_documento") or "CC").upper(),
                    "numero_documento": doc,
                    "primer_nombre": body.get("primer_nombre", ""),
                    "segundo_nombre": body.get("segundo_nombre"),
                    "primer_apellido": body.get("primer_apellido", ""),
                    "segundo_apellido": body.get("segundo_apellido"),
                    "nombre_completo": nombre_comp,
                    "fecha_nacimiento": body.get("fecha_nacimiento", "1990-01-01"),
                    "sexo": (body.get("sexo") or "M").upper(),
                    "telefono": body.get("telefono"),
                    "email": body.get("email"),
                    "direccion": body.get("direccion"),
                    "municipio": body.get("municipio", "Tunja"),
                    "departamento": body.get("departamento", "Boyaca"),
                    "afiliacion": {
                        "eps": body.get("eps") or "Particular",
                        "regimen": "Contributivo" if body.get("eps") and body.get("eps").lower() != "particular" else "Particular",
                        "tipo_afiliado": "Cotizante",
                        "categoria": "A",
                        "estado": "ACTIVO",
                        "fecha_ultima_validacion": hoy().isoformat(),
                    },
                    "empresa": body.get("empresa"),
                    "acepta_whatsapp": body.get("acepta_whatsapp", True),
                }
                resp_ins = await self._client.post("/athenea_pacientes", json=registro, headers={"Prefer": "return=representation"})
                ms = (time.perf_counter() - t0) * 1000
                if resp_ins.status_code in (200, 201):
                    res = resp_ins.json() if resp_ins.text else registro
                    return 201, {"status": "ok", "data": res if isinstance(res, dict) else (res[0] if isinstance(res, list) and res else registro), "mensaje": "Paciente registrado exitosamente"}, ms
                else:
                    return resp_ins.status_code, {"detail": resp_ins.text}, ms
            elif metodo in ("PATCH", "PUT"):
                # Actualización de datos de paciente en Supabase
                doc = ruta.split("/")[-1]
                body = dict(json_body or {})
                if not doc or doc == "pacientes":
                    doc = str(body.pop("numero_documento", ""))
                st_ex, data_ex, _ = await self.get_supabase("athenea_pacientes", {"numero_documento": f"eq.{doc}"})
                if not data_ex or len(data_ex) == 0:
                    return 404, {"detail": f"Paciente con documento {doc} no existe"}, 0
                pac_actual = data_ex[0]
                update_fields = {}
                for k in ("telefono", "email", "direccion", "municipio", "departamento", "empresa", "acepta_whatsapp"):
                    if k in body and body[k] is not None:
                        update_fields[k] = body[k]
                if "eps" in body and body["eps"] is not None:
                    af = pac_actual.get("afiliacion") or {}
                    af["eps"] = body["eps"]
                    update_fields["afiliacion"] = af
                resp_up = await self._client.patch(f"/athenea_pacientes?numero_documento=eq.{doc}", json=update_fields, headers={"Prefer": "return=representation"})
                ms = (time.perf_counter() - t0) * 1000
                if resp_up.status_code in (200, 204):
                    pac_actual.update(update_fields)
                    return 200, {"status": "ok", "data": pac_actual, "mensaje": "Datos de paciente actualizados exitosamente"}, ms
                else:
                    return resp_up.status_code, {"detail": resp_up.text}, ms

        # 2. ATHENEA: Resultados Laboratorio
        elif "laboratorio/resultados" in ruta:
            doc = params.get("numero_documento")
            st, data, ms = await self.get_supabase("athenea_resultados", {"numero_documento": f"eq.{doc}", "order": "fecha_toma.desc"})
            return st, {"status": "ok", "data": data}, ms

        # 3. ATHENEA: Autorizaciones
        elif "autorizaciones" in ruta:
            doc = params.get("numero_documento")
            st, data, ms = await self.get_supabase("athenea_autorizaciones", {"numero_documento": f"eq.{doc}", "order": "fecha_emision.desc"})
            return st, {"status": "ok", "data": data}, ms

        # 3.1 ATHENEA: Catálogo y Precios de Exámenes de Laboratorio (athenea_examenes_laboratorio)
        elif "laboratorio/examenes" in ruta:
            query = {}
            if params.get("nombre"):
                query["examen"] = f"ilike.*{params['nombre']}*"
            st, data, ms = await self.get_supabase("athenea_examenes_laboratorio", query)
            return st, {"status": "ok", "data": data}, ms

        # 3.2 ATHENEA: Tarifas y Convenios EPS (athenea_tarifas)
        elif "tarifas" in ruta:
            query = {}
            if params.get("servicio"):
                query["servicio"] = f"ilike.*{params['servicio']}*"
            if params.get("entidad"):
                query["entidad"] = f"ilike.*{params['entidad']}*"
            st, data, ms = await self.get_supabase("athenea_tarifas", query)
            return st, {"status": "ok", "data": data}, ms

        # 4. IMEDICAL: Disponibilidad Agenda
        elif "agenda/disponibilidad" in ruta:
            esp = params.get("especialidad")
            query = {"especialidad": f"eq.{esp}", "estado": "eq.DISPONIBLE", "order": "fecha.asc,hora.asc"}
            if params.get("sede"):
                query["sede"] = f"ilike.*{params['sede']}*"
            st, data, ms = await self.get_supabase("imedical_agenda", query)
            limite = int(params.get("limite", 5))
            cupos = data[:limite] if isinstance(data, list) else []
            return st, {
                "resultado": cupos,
                "total_cupos_disponibles": len(data) if isinstance(data, list) else 0,
                "primera_fecha_disponible": cupos[0]["fecha"] if cupos else None
            }, ms

        # 5. IMEDICAL: Citas
        elif "citas" in ruta:
            if metodo == "GET":
                doc = params.get("numero_documento")
                st, data, ms = await self.get_supabase("imedical_citas", {"numero_documento": f"eq.{doc}", "order": "fecha_hora.desc"})
                return st, {"resultado": data}, ms
            elif metodo == "POST":
                # Agendamiento completo en Supabase
                id_slot = json_body.get("id_slot")
                doc = json_body.get("numero_documento")

                # 1. Obtener cupo de agenda
                st_slot, data_slot, _ = await self.get_supabase("imedical_agenda", {"id_slot": f"eq.{id_slot}"})
                slot = data_slot[0] if isinstance(data_slot, list) and len(data_slot) > 0 else None
                if not slot:
                    return 404, {"detail": f"El cupo {id_slot} no existe en la agenda de iMedical"}, 0

                # 2. Obtener paciente
                st_pac, data_pac, _ = await self.get_supabase("athenea_pacientes", {"numero_documento": f"eq.{doc}"})
                paciente = data_pac[0] if isinstance(data_pac, list) and len(data_pac) > 0 else {}
                nombre_pac = paciente.get("nombre_completo", f"Paciente CC {doc}")

                # 3. Generar ID de cita y armar registro completo
                import random
                id_cita = f"CIT-{random.randint(100000, 999999)}"
                registro_cita = {
                    "id_cita": id_cita,
                    "numero_documento": str(doc),
                    "paciente": nombre_pac,
                    "id_profesional": slot.get("id_profesional"),
                    "profesional": slot.get("profesional"),
                    "especialidad": slot.get("especialidad"),
                    "sede": slot.get("sede"),
                    "fecha_hora": f"{slot.get('fecha')}T{slot.get('hora')}:00",
                    "estado": "ASIGNADA",
                    "canal_origen": json_body.get("canal_origen", "Copiloto call center"),
                    "numero_autorizacion": json_body.get("numero_autorizacion"),
                    "id_slot": slot.get("id_slot")
                }

                # 4. Insertar cita en Supabase
                resp_ins = await self._client.post("/imedical_citas", json=registro_cita)

                # 5. Marcar cupo como OCUPADO en Supabase
                await self._client.patch(f"/imedical_agenda?id_slot=eq.{id_slot}", json={"estado": "OCUPADO", "id_cita": id_cita})

                ms = (time.perf_counter() - t0) * 1000
                if resp_ins.status_code in (200, 201):
                    return 201, {"resultado": registro_cita, "mensaje": "Cita asignada correctamente"}, ms
                else:
                    return resp_ins.status_code, {"detail": resp_ins.text}, ms

        # 6. IMEDICAL: Liberar cupo / Cancelar cita en Supabase
        elif "liberar" in ruta or "cancelar" in ruta:
            payload = json_body or params or {}
            id_slot = payload.get("id_slot")
            doc = payload.get("numero_documento")
            id_cita = payload.get("id_cita")
            motivo = payload.get("motivo") or "Solicitud de cancelación / liberación de cupo"

            cita_encontrada = None
            slot_id_a_liberar = id_slot

            # 1. Por código de cupo AG-
            if id_slot:
                # 1.1 Verificar existencia del cupo en imedical_agenda
                st_s, slots_s, _ = await self.get_supabase("imedical_agenda", {"id_slot": f"eq.{id_slot}"})
                if not slots_s or len(slots_s) == 0:
                    return 404, {"detail": f"El cupo {id_slot} no existe en la agenda de iMedical"}, 0
                slot_info = slots_s[0]

                # 1.2 Buscar si tiene cita activa asociada
                st_c, citas_s, _ = await self.get_supabase("imedical_citas", {"id_slot": f"eq.{id_slot}", "estado": "in.(ASIGNADA,CONFIRMADA)", "order": "id_cita.desc"})
                if citas_s and len(citas_s) > 0:
                    cita_encontrada = citas_s[0]
                else:
                    c_id_en_slot = slot_info.get("id_cita")
                    if c_id_en_slot:
                        _, citas_c, _ = await self.get_supabase("imedical_citas", {"id_cita": f"eq.{c_id_en_slot}"})
                        if citas_c:
                            cita_encontrada = citas_c[0]
                    if not cita_encontrada:
                        _, citas_hist, _ = await self.get_supabase("imedical_citas", {"id_slot": f"eq.{id_slot}", "order": "id_cita.desc"})
                        if citas_hist:
                            cita_encontrada = citas_hist[0]

            # 2. Por código de cita CIT-
            elif id_cita:
                st_c, citas_c, _ = await self.get_supabase("imedical_citas", {"id_cita": f"eq.{id_cita}"})
                if citas_c and len(citas_c) > 0:
                    cita_encontrada = citas_c[0]
                    slot_id_a_liberar = cita_encontrada.get("id_slot")
                else:
                    return 404, {"detail": f"La cita {id_cita} no existe en iMedical"}, 0

            # 3. Por número de documento del paciente CC
            elif doc:
                st_c, citas_d, _ = await self.get_supabase("imedical_citas", {"numero_documento": f"eq.{doc}", "estado": "in.(ASIGNADA,CONFIRMADA)", "order": "fecha_hora.desc"})
                if citas_d and len(citas_d) > 0:
                    cita_encontrada = citas_d[0]
                    slot_id_a_liberar = cita_encontrada.get("id_slot")
                else:
                    return 404, {"detail": f"El paciente CC {doc} no tiene citas activas pendientes para cancelar en iMedical"}, 0
            else:
                return 400, {"detail": "Debes especificar al menos el código del cupo (id_slot, ej: AG-000255) o la cédula del paciente."}, 0

            # Liberar el cupo en imedical_agenda (estado = 'DISPONIBLE', id_cita = null)
            if slot_id_a_liberar:
                await self._client.patch(f"/imedical_agenda?id_slot=eq.{slot_id_a_liberar}", json={"estado": "DISPONIBLE", "id_cita": None})
                # Cancelar todas las citas activas vinculadas a este cupo
                await self._client.patch(f"/imedical_citas?id_slot=eq.{slot_id_a_liberar}&estado=in.(ASIGNADA,CONFIRMADA)", json={"estado": "CANCELADA"})

            # Cancelar la cita específica encontrada
            if cita_encontrada:
                c_id = cita_encontrada.get("id_cita")
                await self._client.patch(f"/imedical_citas?id_cita=eq.{c_id}", json={"estado": "CANCELADA"})

            ms = (time.perf_counter() - t0) * 1000
            return 200, {
                "resultado": {
                    "id_slot": slot_id_a_liberar,
                    "id_cita": cita_encontrada.get("id_cita") if cita_encontrada else None,
                    "paciente": cita_encontrada.get("paciente") if cita_encontrada else None,
                    "especialidad": cita_encontrada.get("especialidad") if cita_encontrada else None,
                    "fecha_hora": cita_encontrada.get("fecha_hora") if cita_encontrada else None,
                    "estado_cupo": "DISPONIBLE",
                    "estado_cita": "CANCELADA" if cita_encontrada else None,
                    "motivo": motivo
                },
                "mensaje": f"Cupo {slot_id_a_liberar or ''} liberado exitosamente y cita cancelada."
            }, ms

        # 7. SAGICC: Interacciones y PQRS
        elif "interacciones" in ruta:
            doc = params.get("numero_documento")
            st, data, ms = await self.get_supabase("sagicc_interacciones", {"numero_documento": f"eq.{doc}", "order": "fecha_inicio.desc", "limit": params.get("limite", 5)})
            return st, {"data": data}, ms

        elif "pqrs" in ruta:
            doc = params.get("numero_documento")
            st, data, ms = await self.get_supabase("sagicc_pqrs", {"numero_documento": f"eq.{doc}", "order": "fecha_radicacion.desc"})
            return st, {"data": data}, ms

        # Fallback general
        return 200, {"data": []}, 0.0

def os_supabase_configured() -> bool:
    import os
    return bool(os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")))
