"""
Orquestador del agente de IA (Copiloto IPS Carvajal).
Gestiona el ciclo de vida de la conversacion, invocacion de herramientas (Tool Calling)
con Gemini (o fallback por reglas si no hay API key configurada) y emite trazas para la UI.
"""
from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator

from app.clients import ApiClient
from app.config import ahora, hoy, settings
from app.data_store import normalizar
from app.tools import TOOLS_BY_NAME, declaraciones_gemini, ejecutar_tool

SYSTEM_INSTRUCTION = """Eres el Copiloto Inteligente de Atención y Agendamiento de la IPS Carvajal (Tunja, Boyacá).
Tu objetivo es asistir a los colaboradores del contact center / call center para resolver las consultas de los pacientes en un solo lugar y en tiempo récord, reduciendo drásticamente los tiempos de espera y evitando saltar manualmente entre pantallas.

Tienes acceso directo mediante herramientas (tools) a los tres sistemas de la institución:
1. ATHENEA: Datos demográficos del paciente, afiliación a EPS (estado activo/suspendido), autorizaciones médicas, tarifas, cuotas moderadoras, catálogo de exámenes y ESTADO DE RESULTADOS DE LABORATORIO (Listo / En proceso / Entregado).
2. IMEDICAL: Sedes, especialidades, profesionales médicos, consulta de disponibilidad de agenda en tiempo real, historial de citas y resumen clínico básico (alergias, antecedentes CIE-10).
3. SAGICC: Historial de interacciones omnicanal del paciente (WhatsApp, llamadas, web chat), tiempos de espera, tipificaciones, agentes y casos de PQRS radicados.
4. BASE DOCUMENTAL (RAG): Protocolos de preparación de exámenes (ayuno estricto, orina, heces), sedes y horarios en Boyacá, requisitos de convenios EPS y políticas de cancelación.

REGLAS DE OPERACIÓN:
- Sé siempre cortés, claro, estructurado y profesional en español de Colombia.
- REGLA DE ORO: Responde ÚNICAMENTE a lo que el colaborador te preguntó explícitamente.
- PROHIBICIÓN ESTRICTA: NUNCA inventes preguntas ficticias, NO generes diálogos simulados (como 'Usuario: ... / Copiloto: ...' o 'P: ... / R: ...') y NO asumas preguntas futuras que el usuario no ha hecho.
- Si el colaborador únicamente ingresa un número de cédula o documento sin formular una pregunta específica:
  Presenta un resumen ejecutivo directo y puntual del paciente:
  1. Nombre completo y documento
  2. EPS, régimen y estado de afiliación
  3. Si tiene autorizaciones vigentes
  4. Si tiene citas próximas o resultados de laboratorio listos
  Y DETENTE DE INMEDIATO. No agregues preguntas retóricas ni supuestos.
- Cita los sistemas que consultaste para respaldar la respuesta (ej. "En Athenea...", "Según iMedical...").
- GESTIÓN DE LABORATORIO CLÍNICO Y TOMA DE MUESTRAS:
  * Si el usuario consulta el ESTADO DE SUS EXÁMENES O RESULTADOS: ejecuta `consultar_resultados_laboratorio` (Athenea).
  * Si el usuario consulta PRECIOS, TARIFAS o COSTO PARTICULAR de exámenes: ejecuta `consultar_examenes_laboratorio` (Athenea - tabla athenea_examenes_laboratorio) que contiene el código CUPS y el valor en COP.
  * Si el usuario solicita AGENDAR CITA O CONSULTAR CUPOS/HORARIOS PARA LABORATORIO O TOMA DE MUESTRAS: utiliza la especialidad 'Toma de Muestras de Laboratorio' en `consultar_disponibilidad` o `agendar_cita` (iMedical).
  * Informa al usuario que la toma de muestras de rutina en IPS Carvajal también se atiende por orden de llegada en ayunas (6:00 a. m. a 9:30 a. m. en Tunja y Duitama), pero que también se puede agendar cita previa para asegurar turno y evitar filas.
- REGLAS DE AGENDAMIENTO Y CANCELACIÓN:
  * Si el usuario te pide agendar una cita y proporciona el cupo o id_slot (o dice 'agenda el primer cupo disponible'): EJECUTA de inmediato la herramienta `agendar_cita`.
  * Si te pide agendar pero aún no se conocen los cupos, ejecuta primero `consultar_disponibilidad`, muestra las opciones con su respectivo `id_slot` y dile que te indique cuál slot desea confirmar.
  * Si el usuario te pide CANCELAR, ANULAR o LIBERAR un cupo o cita (por código AG-XXXXXX, por radicado CIT-XXXXXX o por CC del paciente): EJECUTA de inmediato la herramienta `liberar_cupo`.
- INGRESO Y MODIFICACIÓN DE DATOS DEL PACIENTE:
  * Si el usuario te pide registrar o dar de alta un nuevo paciente: ejecuta de inmediato la herramienta `registrar_paciente` en Athenea.
  * Si el usuario te pide actualizar o modificar datos de contacto/afiliación/empresa de un paciente: ejecuta de inmediato la herramienta `actualizar_datos_paciente` en Athenea.
- NUNCA inventes cupos, fechas ni resultados médicos; usa las herramientas.
"""

def _extraer_documento(texto: str) -> str | None:
    # 1. Priorizar si viene con prefijo como CC, TI, CE, cédula o documento
    prefijo = re.search(r"(?:cc|ti|ce|documento|c[eé]dula|paciente)\s*[:#]?\s*(\d{6,10})", texto, re.IGNORECASE)
    if prefijo:
        return prefijo.group(1)
    # 2. Si no, buscar números de 6 a 10 dígitos que NO estén precedidos por prefijos como AG-, CIT-, ORD-, o PQRS-
    coincidencias = re.findall(r"(?<![a-zA-Z\-_])\b\d{6,10}\b", texto)
    return coincidencias[0] if coincidencias else None

async def _ejecutar_fallback_inteligente(api: ApiClient, mensaje: str) -> tuple[str, list[dict]]:
    """
    Fallback automático para cuando aún no se ha configurado GEMINI_API_KEY en .env.
    Permite probar el MVP de inmediato identificando intenciones y ejecutando las herramientas reales.
    """
    doc = _extraer_documento(mensaje)
    m = normalizar(mensaje)
    trazas = []
    lineas_resp = []

    slot_match = re.search(r"\bAG-\d+\b", mensaje, re.IGNORECASE)
    cit_match = re.search(r"\bCIT-\d+\b", mensaje, re.IGNORECASE)
    es_cancelacion = bool(("cancel" in m or "liber" in m or "anul" in m or "elimin" in m or "borr" in m) and (slot_match or cit_match or doc or "cupo" in m or "cita" in m))
    es_agendamiento = bool(("agend" in m or "reserv" in m or "asigna" in m or "confirm" in m) and (slot_match or "primer" in m or "cupo" in m))
    es_modificacion = bool(
        ("actualiz" in m or "modific" in m or "cambi" in m) and
        ("telefon" in m or "celular" in m or "correo" in m or "email" in m or "direccion" in m or "empresa" in m or "eps" in m or "datos" in m or "contacto" in m)
    )
    es_registro = bool(
        ("registr" in m or "ingres" in m or "crear" in m or "alta" in m) and
        ("paciente" in m or "usuario" in m or "trabajador" in m or "persona" in m)
    )

    paciente = None
    if doc:
        res_pac, tr_pac = await ejecutar_tool(api, "buscar_paciente", {"numero_documento": doc})
        trazas.append(tr_pac)
        if not res_pac.get("error"):
            paciente = res_pac.get("data")

    def _detectar_especialidad(t: str) -> str:
        if "ocupacional" in t or "ingreso" in t or "egreso" in t or "periodico" in t or "trabajo" in t:
            return "Salud Ocupacional"
        elif "laboratorio" in t or "muestra" in t or "sangre" in t or "bacterio" in t or "ayuno" in t:
            return "Toma de Muestras de Laboratorio"
        elif "interna" in t:
            return "Medicina Interna"
        elif "pediatr" in t:
            return "Pediatria"
        elif "ginec" in t or "obstet" in t:
            return "Ginecologia y Obstetricia"
        elif "cardio" in t:
            return "Cardiologia"
        elif "ortop" in t or "trauma" in t:
            return "Ortopedia y Traumatologia"
        elif "dermat" in t:
            return "Dermatologia"
        elif "nutri" in t:
            return "Nutricion y Dietetica"
        elif "psicol" in t:
            return "Psicologia"
        return "Medicina General"

    es_consulta_agenda = bool(
        ("disponib" in m or "cita" in m or "agenda" in m or "turno" in m or "medico" in m or "horario" in m or "agend" in m or "reserv" in m)
        and not ("resultado" in m and not ("agend" in m or "cita" in m or "disponib" in m or "turno" in m))
    )

    # 1. Caso: Cancelación de cita o liberación de cupo (Máxima prioridad de acción)
    if es_cancelacion:
        slot_id = slot_match.group(0).upper() if slot_match else None
        cita_id = cit_match.group(0).upper() if cit_match else None

        res_lib, tr_lib = await ejecutar_tool(api, "liberar_cupo", {
            "id_slot": slot_id,
            "numero_documento": doc,
            "id_cita": cita_id,
            "motivo": "Cancelación solicitada por el usuario"
        })
        trazas.append(tr_lib)
        if not res_lib.get("error"):
            info = res_lib.get("resultado", {})
            lineas_resp.append("### ✅ ¡Cupo Liberado y Cita Cancelada Exitosamente!")
            if info.get("id_slot"):
                lineas_resp.append(f"- **Cupo de Agenda:** `{info.get('id_slot')}` *(Estado: **DISPONIBLE**)*")
            if info.get("id_cita"):
                lineas_resp.append(f"- **Radicado Cita Cancelada:** `{info.get('id_cita')}`")
            if info.get("paciente"):
                lineas_resp.append(f"- **Paciente:** {info.get('paciente')}")
            if info.get("especialidad"):
                lineas_resp.append(f"- **Especialidad:** {info.get('especialidad')}")
            if info.get("fecha_hora"):
                lineas_resp.append(f"- **Fecha y Hora:** `{info.get('fecha_hora')}`")
            lineas_resp.append("\n> El horario ha vuelto a quedar habilitado en iMedical para que otro paciente pueda tomarlo.")
        else:
            lineas_resp.append(f"### ❌ No fue posible liberar el cupo / cancelar la cita:\n{res_lib.get('detalle')}")

    # 2. Caso: Agendamiento activo (Crear cita en slot específico o primer cupo)
    elif es_agendamiento:
        if not doc:
            lineas_resp.append("Para agendar la cita, por favor indícame el número de cédula o documento del paciente.")
        else:
            slot_id = slot_match.group(0).upper() if slot_match else None
            if not slot_id:
                # Si dice "agenda el primer cupo", buscamos el primer cupo libre
                esp_detectada = _detectar_especialidad(m)
                res_d, _ = await ejecutar_tool(api, "consultar_disponibilidad", {"especialidad": esp_detectada, "limite": 1})
                cupos_d = res_d.get("resultado", [])
                if cupos_d:
                    slot_id = cupos_d[0]["id_slot"]

            if slot_id:
                res_agendar, tr_agendar = await ejecutar_tool(api, "agendar_cita", {
                    "numero_documento": doc,
                    "id_slot": slot_id,
                    "canal_origen": "Copiloto call center",
                    "atencion_particular": "particular" in m
                })
                trazas.append(tr_agendar)
                if not res_agendar.get("error"):
                    cita = res_agendar.get("resultado", {})
                    lineas_resp.append("### ✅ ¡Cita Agendada Exitosamente en iMedical!")
                    lineas_resp.append(f"- **Radicado de Cita:** `{cita.get('id_cita')}`")
                    lineas_resp.append(f"- **Paciente:** {cita.get('paciente')} (CC {doc})")
                    lineas_resp.append(f"- **Especialidad:** {cita.get('especialidad')} con **{cita.get('profesional')}**")
                    lineas_resp.append(f"- **Fecha y Hora:** `{cita.get('fecha_hora')}`")
                    lineas_resp.append(f"- **Sede:** {cita.get('sede')}")
                    lineas_resp.append(f"- **Canal:** {cita.get('canal_origen')}")
                    lineas_resp.append(f"\n> El cupo `{slot_id}` ha sido marcado como **OCUPADO** en iMedical y la cita quedó registrada.")
                else:
                    lineas_resp.append(f"### ❌ No fue posible agendar la cita:\n{res_agendar.get('detalle')}")
            else:
                lineas_resp.append("Por favor especifica el código del cupo (ejemplo: `AG-000038`) o la especialidad deseada.")

    # 2.1 Caso: Modificación y actualización de datos de paciente
    elif es_modificacion:
        if not doc:
            lineas_resp.append("Para actualizar los datos del paciente, por favor proporciona su número de cédula o documento.")
        else:
            payload = {"numero_documento": doc}
            tel_match = re.search(r"\b(3\d{9})\b", mensaje)
            if tel_match:
                payload["telefono"] = tel_match.group(1)
            mail_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", mensaje)
            if mail_match:
                payload["email"] = mail_match.group(0)
            emp_match = re.search(r"(?:empresa|convenio|trabaja en)\s*[:#]?\s*([A-Za-zÁÉÍÓÚáéíóúñÑ0-9\.\s]+?)(?:,|\.|$)", mensaje, re.IGNORECASE)
            if emp_match:
                payload["empresa"] = emp_match.group(1).strip()
            if "eps" in m:
                for nombre_eps in ["Nueva EPS", "Sanitas", "Salud Total", "Famisanar", "Compensar", "Coosalud", "Particular"]:
                    if nombre_eps.lower() in m:
                        payload["eps"] = nombre_eps
                        break

            res_up, tr_up = await ejecutar_tool(api, "actualizar_datos_paciente", payload)
            trazas.append(tr_up)
            if not res_up.get("error"):
                d = res_up.get("data", {})
                lineas_resp.append("### ✅ Datos del Paciente Actualizados Exitosamente (Athenea)")
                lineas_resp.append(f"- **Paciente:** {d.get('nombre_completo', f'CC {doc}')}")
                lineas_resp.append(f"- **Documento:** {d.get('tipo_documento', 'CC')} {doc}")
                if "telefono" in payload:
                    lineas_resp.append(f"- **Nuevo Teléfono:** `{d.get('telefono')}`")
                if "email" in payload:
                    lineas_resp.append(f"- **Nuevo Correo:** `{d.get('email')}`")
                if "empresa" in payload:
                    lineas_resp.append(f"- **Empresa / Convenio:** `{d.get('empresa')}`")
                if "eps" in payload:
                    lineas_resp.append(f"- **Nueva EPS:** `{d.get('afiliacion', {}).get('eps')}`")
                lineas_resp.append("\n> La información demográfica y de contacto se ha guardado en el maestro de pacientes.")
            else:
                lineas_resp.append(f"### ❌ No fue posible actualizar los datos del paciente:\n{res_up.get('detalle')}")

    # 2.2 Caso: Registro o ingreso de nuevo paciente
    elif es_registro:
        if not doc:
            lineas_resp.append("Para ingresar un nuevo paciente a Athenea, por favor indícame su número de cédula, nombres, apellidos y fecha de nacimiento (AAAA-MM-DD).")
        else:
            tel_match = re.search(r"\b(3\d{9})\b", mensaje)
            mail_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", mensaje)
            emp_match = re.search(r"(?:empresa|convenio)\s*[:#]?\s*([A-Za-zÁÉÍÓÚáéíóúñÑ0-9\.\s]+?)(?:,|\.|$)", mensaje, re.IGNORECASE)

            res_reg, tr_reg = await ejecutar_tool(api, "registrar_paciente", {
                "numero_documento": doc,
                "primer_nombre": "Nuevo",
                "primer_apellido": "Paciente",
                "fecha_nacimiento": "1995-01-01",
                "telefono": tel_match.group(1) if tel_match else None,
                "email": mail_match.group(0) if mail_match else None,
                "empresa": emp_match.group(1).strip() if emp_match else None,
            })
            trazas.append(tr_reg)
            if not res_reg.get("error"):
                d = res_reg.get("data", {})
                lineas_resp.append("### ✅ Paciente Ingresado Exitosamente a Athenea")
                lineas_resp.append(f"- **ID Asignado:** `{d.get('id_paciente')}`")
                lineas_resp.append(f"- **Documento:** {d.get('tipo_documento', 'CC')} {doc}")
                lineas_resp.append(f"- **Nombre:** {d.get('nombre_completo')}")
                lineas_resp.append(f"- **Empresa:** {d.get('empresa') or 'No registra'}")
                lineas_resp.append(f"- **Estado de Afiliación:** `{d.get('afiliacion', {}).get('estado', 'ACTIVO')}`")
            else:
                lineas_resp.append(f"### ⚠️ Aviso al registrar paciente:\n{res_reg.get('detalle')}")

    # 3. Caso: Disponibilidad y Consulta de Citas / Agenda Médica / Laboratorio
    elif es_consulta_agenda:
        esp_detectada = _detectar_especialidad(m)

        res_disp, tr_disp = await ejecutar_tool(api, "consultar_disponibilidad", {"especialidad": esp_detectada, "limite": 5})
        trazas.append(tr_disp)
        cupos = res_disp.get("resultado", [])

        lineas_resp.append(f"### Disponibilidad para {esp_detectada} (iMedical):")
        if cupos:
            lineas_resp.append(f"Primera fecha disponible: **{res_disp.get('primera_fecha_disponible')}** ({res_disp.get('total_cupos_disponibles')} cupos libres encontrados):\n")
            for c in cupos:
                lineas_resp.append(f"- **{c['fecha']} a las {c['hora']}** | {c['profesional']} | {c['sede']} *(Slot: `{c['id_slot']}`)*")
            lineas_resp.append(f"\n> [!TIP]\n> Para agendar en uno de estos cupos, responde: **\"Agendar slot {cupos[0]['id_slot']} para CC {doc or '...'}\"**")
        else:
            lineas_resp.append(f"No hay cupos disponibles de inmediato para {esp_detectada}.")

        if esp_detectada == "Toma de Muestras de Laboratorio":
            lineas_resp.append("\n> [!NOTE]\n> **Toma de muestras en IPS Carvajal:** La toma de muestras de laboratorio de rutina (sangre, orina, heces) también se atiende **por orden de llegada en ayunas** (Lunes a Sábado de 6:00 a. m. a 9:30 a. m.) sin cita previa obligatoria. Sin embargo, agendar uno de los cupos anteriores garantiza turno preferencial para evitar filas o para pruebas especiales (ej. Curva de Glucosa PTOG).")

        if paciente and esp_detectada != "Toma de Muestras de Laboratorio":
            res_aut, tr_aut = await ejecutar_tool(api, "consultar_autorizaciones", {"numero_documento": doc})
            trazas.append(tr_aut)
            vig = [a for a in res_aut.get("data", []) if a.get("estado") == "VIGENTE" and a.get("especialidad") == esp_detectada]
            if vig:
                lineas_resp.append(f"\n> [!NOTE]\n> El paciente cuenta con autorización vigente `{vig[0]['numero_autorizacion']}` para {esp_detectada}.")
            elif res_disp.get("requiere_autorizacion"):
                lineas_resp.append(f"\n> [!WARNING]\n> El paciente NO tiene autorización vigente para {esp_detectada} en Athenea. Requiere autorización de su EPS o pago particular.")

    # 4. Caso: Consulta de paciente / ficha 360
    elif paciente and ("quien es" in m or "informacion" in m or "datos" in m or len(m.split()) <= 4):
        p = paciente
        afil = p.get("afiliacion", {})
        lineas_resp.append(f"### Ficha del Paciente: {p['nombre_completo']}")
        lineas_resp.append(f"- **Documento:** {p['tipo_documento']} {p['numero_documento']} (Edad: {p.get('edad', 'N/D')} años)")
        lineas_resp.append(f"- **Empresa / Convenio:** **{p.get('empresa') or 'No registra / Particular'}**")
        lineas_resp.append(f"- **Municipio:** {p.get('municipio')} ({p.get('direccion')})")
        lineas_resp.append(f"- **Teléfono:** {p.get('telefono')}")
        lineas_resp.append(f"- **EPS:** {afil.get('eps') or 'Particular'} | **Régimen:** {afil.get('regimen')} (Cat. {afil.get('categoria', 'N/A')})")
        lineas_resp.append(f"- **Estado de Afiliación:** `{afil.get('estado')}`")

        # Consultar autorizaciones y citas automáticamente
        res_aut, tr_aut = await ejecutar_tool(api, "consultar_autorizaciones", {"numero_documento": doc})
        trazas.append(tr_aut)
        auts = res_aut.get("data", [])
        vigentes = [a for a in auts if a.get("estado") == "VIGENTE"]
        if vigentes:
            lineas_resp.append(f"\n**Autorizaciones vigentes ({len(vigentes)}):**")
            for a in vigentes:
                lineas_resp.append(f"- `{a['numero_autorizacion']}`: {a['especialidad']} (Vence: {a['fecha_vencimiento']})")

        res_cit, tr_cit = await ejecutar_tool(api, "consultar_citas_paciente", {"numero_documento": doc, "solo_futuras": True})
        trazas.append(tr_cit)
        citas_fut = res_cit.get("resultado", [])
        if citas_fut:
            lineas_resp.append(f"\n**Próximas citas programadas ({len(citas_fut)}):**")
            for c in citas_fut:
                lineas_resp.append(f"- {c['especialidad']} con {c['profesional']} el `{c['fecha_hora']}` ({c['sede']})")

    # 5. Caso: Consulta de Precios y Tarifas de Exámenes (Athenea - athenea_examenes_laboratorio)
    elif "precio" in m or "costo" in m or "cuanto cuesta" in m or "cuánto cuesta" in m or "valor" in m or "tarifa" in m:
        filtro_examen = None
        for palabra in ["hemograma", "glucosa", "colesterol", "trigliceridos", "creatinina", "uroanalisis", "orina", "coprologico", "coproscopico", "embarazo", "hcg", "tsh", "hba1c", "glicosilada", "curva"]:
            if palabra in m:
                filtro_examen = palabra
                break

        res_ex, tr_ex = await ejecutar_tool(api, "consultar_examenes_laboratorio", {"nombre": filtro_examen or ""})
        trazas.append(tr_ex)
        lista_examenes = res_ex.get("data", [])
        if lista_examenes:
            lineas_resp.append("### Catálogo y Precios de Exámenes de Laboratorio (Athenea):")
            lineas_resp.append("Tarifas particulares vigentes en la IPS Carvajal:\n")
            for e in lista_examenes[:10]:
                val = f"${e['valor_particular']:,} COP" if isinstance(e.get("valor_particular"), (int, float)) else e.get("valor_particular")
                lineas_resp.append(f"- **{e['examen']}** (CUPS: `{e['codigo_cups']}`): **{val}**")
            lineas_resp.append("\n> [!NOTE]\n> Si el paciente cuenta con afiliación activa a su EPS y autorización médica vigente, el examen estará cubierto por el convenio y solo aplicará la cuota moderadora según su categoría de afiliación.")
        else:
            lineas_resp.append("No se encontraron exámenes de laboratorio con el término buscado en Athenea.")

    # 6. Caso: Consulta de Resultados de Laboratorio
    elif "resultado" in m or "laboratorio" in m or "examen" in m:
        if doc:
            res_lab, tr_lab = await ejecutar_tool(api, "consultar_resultados_laboratorio", {"numero_documento": doc})
            trazas.append(tr_lab)
            ordenes = res_lab.get("data", [])
            if ordenes:
                lineas_resp.append(f"### Estado de Resultados de Laboratorio (Athenea)")
                lineas_resp.append(f"Paciente con documento `{doc}` tiene **{len(ordenes)} orden(es)** registradas:")
                for ord_item in ordenes:
                    examenes_str = ", ".join(ord_item.get("examenes", []))
                    lineas_resp.append(f"\n- **Orden:** `{ord_item['id_orden']}` (Fecha de toma: {ord_item['fecha_toma']})")
                    lineas_resp.append(f"  - **Exámenes:** {examenes_str}")
                    lineas_resp.append(f"  - **Estado:** `{ord_item['estado']}`")
                    lineas_resp.append(f"  - **Canal de entrega:** {ord_item.get('canal_entrega')} (Sede: {ord_item.get('sede_toma')})")
            else:
                lineas_resp.append(f"No se encontraron órdenes de laboratorio recientes en Athenea para el documento `{doc}`.")
        else:
            # Consulta general de preparación o catálogo
            res_rag, tr_rag = await ejecutar_tool(api, "buscar_documentacion", {"pregunta": mensaje})
            trazas.append(tr_rag)
            frags = res_rag.get("fragmentos", [])
            if frags:
                lineas_resp.append(f"### Información de Laboratorio y Preparación:")
                for f in frags[:2]:
                    lineas_resp.append(f"**{f['documento']} - {f['seccion']}:**\n{f['texto']}\n")

    # 4. Caso: PQRS
    elif "pqrs" in m or "queja" in m or "reclamo" in m:
        if doc:
            res_pq, tr_pq = await ejecutar_tool(api, "consultar_pqrs", {"numero_documento": doc})
            trazas.append(tr_pq)
            lista_pqrs = res_pq.get("data", [])
            if lista_pqrs:
                lineas_resp.append(f"### PQRS del Paciente (SAGICC)")
                for p in lista_pqrs:
                    venc_aviso = "⚠️ VENCIDA" if p.get("vencida") else "En tiempo legal"
                    lineas_resp.append(f"- Radicado `{p['radicado']}`: **{p['tipo']}** ({p['motivo']})")
                    lineas_resp.append(f"  - Estado: `{p['estado']}` | Límite respuesta: {p['fecha_limite_respuesta']} ({venc_aviso})")
                    lineas_resp.append(f"  - Área: {p.get('area_responsable')}")
            else:
                lineas_resp.append(f"El paciente `{doc}` no tiene PQRS radicadas en SAGICC.")
        else:
            res_rag, tr_rag = await ejecutar_tool(api, "buscar_documentacion", {"pregunta": "pqrs tiempos respuesta"})
            trazas.append(tr_rag)
            for f in res_rag.get("fragmentos", [])[:1]:
                lineas_resp.append(f"### Información de PQRS:\n{f['texto']}")

    # 5. Consulta documental general (RAG)
    else:
        res_rag, tr_rag = await ejecutar_tool(api, "buscar_documentacion", {"pregunta": mensaje})
        trazas.append(tr_rag)
        frags = res_rag.get("fragmentos", [])
        if frags:
            lineas_resp.append(f"### Información institucional (Base de Conocimiento Carvajal):")
            for f in frags[:2]:
                lineas_resp.append(f"\n**{f['documento']} - {f['seccion']}:**\n{f['texto']}")
        else:
            lineas_resp.append("Hola. Soy el Copiloto de Atención de IPS Carvajal. Puedes consultarme por la cédula de un paciente, disponibilidad de agendas médicas, estado de exámenes de laboratorio en Athenea o radicación de PQRS.")

    return "\n".join(lineas_resp), trazas

async def procesar_mensaje(historial: list[dict], mensaje: str) -> dict[str, Any]:
    """
    Procesa un mensaje de usuario:
    1. Si hay GEMINI_API_KEY configurada, orquesta Gemini 2.5 Flash con llamadas a Tools en loop.
    2. Si no, usa el motor de reglas/intenciones ejecutando exactamente las mismas Tools para garantizar funcionamiento.
    Devuelve: { 'respuesta': markdown, 'trazas': [...], 'paciente': {...} }
    """
    async with ApiClient() as api:
        # Modo con LLM Google Gemini
        if settings.llm_configurado:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=settings.gemini_api_key)
                
                # Convertir herramientas al formato Gemini
                gemini_tools = [types.Tool(function_declarations=[
                    types.FunctionDeclaration(
                        name=t.name,
                        description=t.description,
                        parameters=t.parameters
                    ) for t in TOOLS_BY_NAME.values()
                ])]

                # Construir contenidos
                contents = []
                for h in historial:
                    rol = "user" if h.get("role") == "user" else "model"
                    contents.append(types.Content(role=rol, parts=[types.Part.from_text(text=h.get("content", ""))]))
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=mensaje)]))

                config = types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=gemini_tools,
                    temperature=0.0,
                    stop_sequences=["Usuario:", "Colaborador:", "Pregunta:", "\nUser:", "User:"],
                )

                trazas = []
                # Bucle de Tool Calling (hasta 4 turnos de herramientas)
                for _ in range(4):
                    resp = await client.aio.models.generate_content(
                        model=settings.gemini_model,
                        contents=contents,
                        config=config
                    )

                    # Verificar si el modelo solicitó llamadas a funciones
                    function_calls = resp.function_calls
                    if not function_calls:
                        # Respuesta final de texto generada
                        texto_final = resp.text or ""
                        # Extraer ficha del paciente si se consultó
                        paciente_data = None
                        for t in trazas:
                            if t.get("tool") == "buscar_paciente" and t.get("status") == 200:
                                paciente_data = t.get("resultado")
                        return {"respuesta": texto_final, "trazas": trazas, "paciente": paciente_data}

                    # Ejecutar las funciones solicitadas
                    contents.append(resp.candidates[0].content)
                    tool_parts = []
                    for fc in function_calls:
                        fn_name = fc.name
                        fn_args = dict(fc.args) if fc.args else {}
                        resultado_tool, traza = await ejecutar_tool(api, fn_name, fn_args)
                        trazas.append(traza)
                        tool_parts.append(types.Part.from_function_response(
                            name=fn_name,
                            response={"result": resultado_tool}
                        ))
                    contents.append(types.Content(role="user", parts=tool_parts))

                # Si agotó turnos, retornar lo acumulado
                return {"respuesta": resp.text or "Proceso completado.", "trazas": trazas}

            except Exception as exc:
                print(f"[Aviso Gemini fallback]: {exc}")
                # Fallback suave en caso de error de cuota o clave
                texto_fallback, trazas_fallback = await _ejecutar_fallback_inteligente(api, mensaje)
                return {
                    "respuesta": f"> [!NOTE]\n> *Modo de contingencia activo ({type(exc).__name__})*\n\n" + texto_fallback,
                    "trazas": trazas_fallback
                }

        # Modo sin Gemini API key (Fallback inteligente directo)
        texto, trazas = await _ejecutar_fallback_inteligente(api, mensaje)
        return {"respuesta": texto, "trazas": trazas}
