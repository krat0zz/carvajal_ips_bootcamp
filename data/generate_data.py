"""
Generador de datos sinteticos para el MVP "Copiloto IPS Carvajal".

Simula la informacion que exponen los tres sistemas de la IPS:
  - Athenea  : pacientes, afiliacion (EPS), autorizaciones, tarifas, cuotas moderadoras,
               LABORATORIO (catalogo de examenes, ordenes y estado de resultados).
  - iMedical : sedes, especialidades, profesionales, agenda, citas, resumen clinico.
  - SAGICC   : agentes, interacciones (voz / WhatsApp / web) y PQRS.

TODOS LOS DATOS SON FICTICIOS. La cedula (numero_documento) es la llave comun
entre los tres sistemas, igual que en la operacion real.

Las fechas se generan alrededor de FECHA_ANCLA; en tiempo de ejecucion el
servidor las desplaza (en semanas completas) para que la agenda siempre luzca
"vigente" el dia de la demo.

Uso:
    py data/generate_data.py
"""
from __future__ import annotations

import json
import math
import random
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker

SEED = 2026
FECHA_ANCLA = date(2026, 10, 16)  # viernes
OUT_DIR = Path(__file__).resolve().parent / "generated"

N_PACIENTES = 400
DIAS_AGENDA = 15          # dias habiles futuros con agenda
DIAS_HISTORIA = 90        # dias calendario hacia atras para citas pasadas
N_INTERACCIONES = 1800
DIAS_INTERACCIONES = 30
N_PQRS = 150

fake = Faker("es_CO")
Faker.seed(SEED)
rng = random.Random(SEED)

# --------------------------------------------------------------------------------------
# Catalogos
# --------------------------------------------------------------------------------------
MUNICIPIOS = {
    "Tunja": 50, "Duitama": 12, "Sogamoso": 9, "Paipa": 6, "Villa de Leyva": 4,
    "Samaca": 4, "Ventaquemada": 4, "Chiquinquira": 3, "Toca": 2, "Motavita": 3,
    "Oicata": 2, "Soraca": 2,
}
EPS_CONTRIBUTIVO = ["Nueva EPS", "Sanitas", "Salud Total", "Famisanar", "Compensar"]
EPS_SUBSIDIADO = ["Nueva EPS", "Coosalud", "Famisanar"]

SEDES = [
    {"codigo": "CEN", "nombre": "Sede Centro Tunja", "direccion": "Calle 19 # 10-45, Tunja (ficticia)",
     "telefono": "608 742 0000 (ficticio)", "horario": "Lun-Vie 6:00 a. m.-6:00 p. m.; Sab 6:00 a. m.-12:00 m."},
    {"codigo": "NOR", "nombre": "Sede Norte Tunja", "direccion": "Avenida Norte # 45-20, Tunja (ficticia)",
     "telefono": "608 742 0001 (ficticio)", "horario": "Lun-Vie 6:00 a. m.-6:00 p. m.; Sab 7:00 a. m.-12:00 m."},
    {"codigo": "DUI", "nombre": "Sede Duitama", "direccion": "Carrera 16 # 14-30, Duitama (ficticia)",
     "telefono": "608 760 0002 (ficticio)", "horario": "Lun-Vie 6:00 a. m.-5:00 p. m."},
]
SEDES_TODAS = [s["nombre"] for s in SEDES]

ESPECIALIDADES = [
    dict(nombre="Medicina General", cups="890201", servicio="Consulta de primera vez por medicina general",
         duracion=20, sedes=SEDES_TODAS, requiere_autorizacion=False, n_prof=5, edad=(0, 120), sexo=None,
         tarifa=48000, peso=40, ocupacion_extra=0.04),
    dict(nombre="Medicina Interna", cups="890266", servicio="Consulta de primera vez por medicina interna",
         duracion=20, sedes=["Sede Centro Tunja", "Sede Norte Tunja"], requiere_autorizacion=True, n_prof=2,
         edad=(15, 120), sexo=None, tarifa=95000, peso=6, ocupacion_extra=0.07),
    dict(nombre="Pediatria", cups="890283", servicio="Consulta de primera vez por pediatria",
         duracion=20, sedes=["Sede Centro Tunja", "Sede Duitama"], requiere_autorizacion=True, n_prof=2,
         edad=(0, 17), sexo=None, tarifa=90000, peso=8, ocupacion_extra=0.03),
    dict(nombre="Ginecologia y Obstetricia", cups="890250", servicio="Consulta de primera vez por ginecologia y obstetricia",
         duracion=20, sedes=["Sede Centro Tunja"], requiere_autorizacion=True, n_prof=2,
         edad=(14, 120), sexo="F", tarifa=95000, peso=6, ocupacion_extra=0.05),
    dict(nombre="Ortopedia y Traumatologia", cups="890280", servicio="Consulta de primera vez por ortopedia y traumatologia",
         duracion=20, sedes=["Sede Norte Tunja"], requiere_autorizacion=True, n_prof=1,
         edad=(0, 120), sexo=None, tarifa=100000, peso=4, ocupacion_extra=0.08),
    dict(nombre="Dermatologia", cups="890242", servicio="Consulta de primera vez por dermatologia",
         duracion=20, sedes=["Sede Centro Tunja"], requiere_autorizacion=True, n_prof=1,
         edad=(0, 120), sexo=None, tarifa=100000, peso=4, ocupacion_extra=0.08),
    dict(nombre="Cardiologia", cups="890228", servicio="Consulta de primera vez por cardiologia",
         duracion=30, sedes=["Sede Centro Tunja"], requiere_autorizacion=True, n_prof=1,
         edad=(18, 120), sexo=None, tarifa=120000, peso=4, ocupacion_extra=0.08),
    dict(nombre="Nutricion y Dietetica", cups="890206", servicio="Consulta de primera vez por nutricion y dietetica",
         duracion=30, sedes=["Sede Norte Tunja", "Sede Duitama"], requiere_autorizacion=False, n_prof=1,
         edad=(0, 120), sexo=None, tarifa=60000, peso=3, ocupacion_extra=0.0),
    dict(nombre="Psicologia", cups="890208", servicio="Consulta de primera vez por psicologia",
         duracion=40, sedes=["Sede Centro Tunja"], requiere_autorizacion=False, n_prof=1,
         edad=(5, 120), sexo=None, tarifa=70000, peso=3, ocupacion_extra=0.02),
    dict(nombre="Toma de Muestras de Laboratorio", cups="LAB-TM", servicio="Toma de muestras de laboratorio clinico",
         duracion=10, sedes=SEDES_TODAS, requiere_autorizacion=False, n_prof=3, edad=(0, 120), sexo=None,
         tarifa=0, peso=22, ocupacion_extra=-0.30),
    dict(nombre="Salud Ocupacional", cups="890205", servicio="Examen medico ocupacional de ingreso y periodico",
         duracion=20, sedes=SEDES_TODAS, requiere_autorizacion=False, n_prof=2, edad=(18, 75), sexo=None,
         tarifa=45000, peso=10, ocupacion_extra=-0.10),
]
ESP_BY_NAME = {e["nombre"]: e for e in ESPECIALIDADES}

EMPRESAS_COLOMBIA = [
    "Acerías Paz del Río S.A.", "Postobón S.A.", "Bavaria & Cía S.C.A.", "Cementos Argos S.A.",
    "Ecopetrol S.A.", "Grupo Nutresa S.A.S.", "Alcaldía Mayor de Tunja", "Gobernación de Boyacá",
    "Carvajal Tecnología y Servicios S.A.S.", "Empresa de Energía de Boyacá (EBSA)", "Holcim Colombia S.A.",
    "Comfaboy", "Hospital Universitario San Rafael de Tunja", "Servientrega S.A.", "D1 S.A.S. (Koba Colombia)",
    "Almacenes Éxito S.A.", "Transportes Concorde S.A.", "Coflonorte / Libertadores S.A.",
    "Lácteos La Alquería Boyacá", "Mina El Cerrejón / Carbones de Boyacá"
]

# Codigos de referencia ficticios para el MVP (estilo CUPS).
EXAMENES_LAB = [
    ("902210", "Hemograma completo", 22000),
    ("903841", "Glucosa en suero", 9000),
    ("903844", "Curva de tolerancia oral a la glucosa", 38000),
    ("903818", "Colesterol total", 10000),
    ("903815", "Colesterol HDL", 13000),
    ("903868", "Trigliceridos", 11000),
    ("903895", "Creatinina en suero", 10000),
    ("903426", "Hemoglobina glicosilada (HbA1c)", 42000),
    ("907106", "Uroanalisis (parcial de orina)", 12000),
    ("907002", "Coprologico", 12000),
    ("904508", "Prueba de embarazo en sangre (HCG cuantitativa)", 35000),
    ("904903", "Hormona estimulante de tiroides (TSH)", 32000),
]

CIE10 = [
    ("I10", "Hipertension esencial (primaria)", 45),
    ("E11", "Diabetes mellitus tipo 2", 45),
    ("E78", "Trastornos del metabolismo de lipoproteinas", 35),
    ("J45", "Asma", 5),
    ("E03", "Hipotiroidismo", 25),
    ("M54", "Dorsalgia", 25),
    ("K29", "Gastritis y duodenitis", 18),
    ("F41", "Trastorno de ansiedad", 18),
    ("N39", "Infeccion de vias urinarias, sitio no especificado", 5),
]
ALERGIAS = {"Ninguna conocida": 80, "Penicilina": 7, "AINES": 5, "Sulfas": 3, "Latex": 2, "Mariscos": 3}
GRUPOS_SANGUINEOS = {"O+": 58, "A+": 26, "B+": 8, "O-": 3, "AB+": 2, "A-": 2, "B-": 1}

AGENTES_SAGICC = [
    "Diana Carolina Moreno", "Johan Sebastian Rincon", "Paola Andrea Vargas", "Cristian Camilo Suarez",
    "Leidy Johanna Pena", "Oscar Ivan Ramirez", "Yuly Marcela Cardenas", "Edwin Fabian Huertas",
]

# --------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------

def wchoice(opciones: dict):
    return rng.choices(list(opciones), weights=list(opciones.values()))[0]


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def es_habil(d: date) -> bool:
    return d.weekday() < 5


def sumar_habiles(d: date, n: int) -> date:
    paso = 1 if n >= 0 else -1
    restantes = abs(n)
    actual = d
    while restantes:
        actual += timedelta(days=paso)
        if es_habil(actual):
            restantes -= 1
    return actual


def habiles_entre(a: date, b: date) -> int:
    """Dias habiles transcurridos de a hasta b (a < b)."""
    n, actual = 0, a
    while actual < b:
        actual += timedelta(days=1)
        if es_habil(actual):
            n += 1
    return n


def dias_habiles_futuros(n: int) -> list[date]:
    dias, actual = [], FECHA_ANCLA
    while len(dias) < n:
        actual += timedelta(days=1)
        if es_habil(actual):
            dias.append(actual)
    return dias


def dia_habil_pasado(max_dias: int, min_dias: int = 1) -> date:
    while True:
        d = FECHA_ANCLA - timedelta(days=rng.randint(min_dias, max_dias))
        if es_habil(d):
            return d


def edad_en(fecha_nac: date, ref: date = FECHA_ANCLA) -> int:
    return ref.year - fecha_nac.year - ((ref.month, ref.day) < (fecha_nac.month, fecha_nac.day))


def horas_bloque(inicio: str, fin: str, duracion: int) -> list[str]:
    h0 = datetime.strptime(inicio, "%H:%M")
    h1 = datetime.strptime(fin, "%H:%M")
    horas = []
    while h0 + timedelta(minutes=duracion) <= h1:
        horas.append(h0.strftime("%H:%M"))
        h0 += timedelta(minutes=duracion)
    return horas


def iso(d: date) -> str:
    return d.isoformat()


def iso_dt(d: date, hora: str) -> str:
    return f"{d.isoformat()}T{hora}:00"


def telefono() -> str:
    pref = rng.choice(["300", "301", "310", "311", "312", "313", "314", "315", "316", "320", "321", "322", "350"])
    return f"{pref}{rng.randint(1000000, 9999999)}"


_contadores: dict[str, int] = {}


def nuevo_id(prefijo: str, ancho: int = 6) -> str:
    _contadores[prefijo] = _contadores.get(prefijo, 0) + 1
    return f"{prefijo}{_contadores[prefijo]:0{ancho}d}"


# --------------------------------------------------------------------------------------
# Estructuras de salida
# --------------------------------------------------------------------------------------
athenea = {"pacientes": [], "autorizaciones": [], "tarifas": [], "cuotas_moderadoras": [],
           "examenes_laboratorio": [{"codigo_cups": c, "examen": n, "valor_particular": v} for c, n, v in EXAMENES_LAB],
           "resultados": []}
imedical = {"sedes": SEDES, "especialidades": [], "profesionales": [], "agenda": [], "citas": [],
            "historias": []}
sagicc = {"agentes": [], "interacciones": [], "pqrs": []}

documentos_usados: set[str] = set()

# --------------------------------------------------------------------------------------
# Catalogos de iMedical: especialidades, profesionales, agenda
# --------------------------------------------------------------------------------------

def generar_catalogos() -> None:
    for e in ESPECIALIDADES:
        imedical["especialidades"].append({
            "especialidad": e["nombre"], "codigo_cups": e["cups"], "servicio": e["servicio"],
            "duracion_min": e["duracion"], "sedes": e["sedes"], "requiere_autorizacion": e["requiere_autorizacion"],
            "restriccion_edad": {"min": e["edad"][0], "max": e["edad"][1]},
            "restriccion_sexo": e["sexo"],
        })
        for i in range(e["n_prof"]):
            sexo = rng.choice(["F", "M"])
            nombre = (fake.first_name_female() if sexo == "F" else fake.first_name_male())
            nombre = f"{nombre} {fake.last_name()} {fake.last_name()}"
            titulo = "Bact." if e["nombre"].startswith("Toma") else ("Ps." if e["nombre"] == "Psicologia" else
                     ("Nut." if e["nombre"].startswith("Nutricion") else ("Dra." if sexo == "F" else "Dr.")))
            if e["nombre"].startswith("Toma"):
                bloque = ("06:00", "10:00")
            else:
                bloque = ("07:00", "11:00") if i % 2 == 0 else ("14:00", "18:00")
            imedical["profesionales"].append({
                "id_profesional": nuevo_id("IM-PRO-", 3),
                "nombre": f"{titulo} {nombre}",
                "especialidad": e["nombre"],
                "sede": e["sedes"][i % len(e["sedes"])],
                "registro_medico": f"RM-{rng.randint(10000, 99999)}-BOY",
                "jornada": f"{bloque[0]}-{bloque[1]}",
            })


def generar_agenda() -> None:
    for d_idx, dia in enumerate(dias_habiles_futuros(DIAS_AGENDA)):
        base = 0.92 if d_idx < 5 else (0.72 if d_idx < 10 else 0.40)
        for prof in imedical["profesionales"]:
            esp = ESP_BY_NAME[prof["especialidad"]]
            ocupacion = max(0.05, min(0.98, base + esp["ocupacion_extra"]))
            inicio, fin = prof["jornada"].split("-")
            for hora in horas_bloque(inicio, fin, esp["duracion"]):
                r = rng.random()
                estado = "BLOQUEADO" if r < 0.03 else ("OCUPADO" if r < 0.03 + ocupacion else "DISPONIBLE")
                imedical["agenda"].append({
                    "id_slot": nuevo_id("AG-"),
                    "id_profesional": prof["id_profesional"],
                    "profesional": prof["nombre"],
                    "especialidad": prof["especialidad"],
                    "sede": prof["sede"],
                    "fecha": iso(dia),
                    "hora": hora,
                    "duracion_min": esp["duracion"],
                    "estado": estado,
                    "id_cita": None,
                })


def generar_tarifas() -> None:
    entidades = sorted(set(EPS_CONTRIBUTIVO + EPS_SUBSIDIADO)) + ["Particular"]
    servicios = [(e["cups"], e["servicio"], e["tarifa"]) for e in ESPECIALIDADES if e["tarifa"]]
    servicios += EXAMENES_LAB
    for cups, servicio, base in servicios:
        for ent in entidades:
            factor = 1.0 if ent == "Particular" else rng.choice([0.72, 0.78, 0.82, 0.86, 0.9])
            athenea["tarifas"].append({
                "codigo_cups": cups, "servicio": servicio, "entidad": ent,
                "valor": int(round(base * factor, -2)),
                "moneda": "COP",
                "tipo": "Tarifa particular" if ent == "Particular" else "Tarifa convenio EPS",
            })
    athenea["cuotas_moderadoras"] = [
        {"regimen": "Contributivo", "categoria": "A", "cuota_moderadora": 4800, "copago_porcentaje": 11.5},
        {"regimen": "Contributivo", "categoria": "B", "cuota_moderadora": 19100, "copago_porcentaje": 17.3},
        {"regimen": "Contributivo", "categoria": "C", "cuota_moderadora": 50300, "copago_porcentaje": 23.0},
        {"regimen": "Subsidiado", "categoria": "Sisben A/B", "cuota_moderadora": 0, "copago_porcentaje": 0.0},
        {"regimen": "Subsidiado", "categoria": "Sisben C", "cuota_moderadora": 0, "copago_porcentaje": 10.0},
    ]
    for c in athenea["cuotas_moderadoras"]:
        c["nota"] = "Valores ficticios de referencia para el MVP"


# --------------------------------------------------------------------------------------
# Pacientes y su informacion asociada
# --------------------------------------------------------------------------------------

def documento_para(edad: int) -> tuple[str, str]:
    while True:
        if rng.random() < 0.03 and edad >= 18:
            tipo, num = "CE", str(rng.randint(100000, 999999))
        elif edad < 7:
            tipo, num = "RC", str(rng.randint(1_051_000_000, 1_059_999_999))
        elif edad < 18:
            tipo, num = "TI", str(rng.randint(1_051_000_000, 1_059_999_999))
        elif edad > 45:
            tipo = "CC"
            num = str(rng.choice([rng.randint(4_000_000, 7_999_999), rng.randint(23_000_000, 24_999_999),
                                  rng.randint(40_000_000, 40_099_999)]))
        else:
            tipo, num = "CC", str(rng.choice([rng.randint(1_049_000_000, 1_053_999_999),
                                              rng.randint(1_002_000_000, 1_007_999_999)]))
        if num not in documentos_usados:
            documentos_usados.add(num)
            return tipo, num


def crear_paciente(**fijo) -> dict:
    if "fecha_nacimiento" in fijo:
        fnac = date.fromisoformat(fijo["fecha_nacimiento"])
    else:
        rango = wchoice({(0, 5): 7, (6, 17): 13, (18, 29): 18, (30, 44): 22, (45, 59): 20, (60, 85): 20})
        edad = rng.randint(*rango)
        fnac = FECHA_ANCLA - timedelta(days=edad * 365 + rng.randint(0, 364))
    edad = edad_en(fnac)
    sexo = fijo.get("sexo") or rng.choice(["F", "M"])
    if "numero_documento" in fijo:
        tipo, num = fijo["tipo_documento"], fijo["numero_documento"]
        documentos_usados.add(num)
    else:
        tipo, num = documento_para(edad)

    if "nombres" in fijo:
        n1, n2, a1, a2 = fijo["nombres"]
    else:
        gen = fake.first_name_female if sexo == "F" else fake.first_name_male
        n1, n2 = gen(), (gen() if rng.random() < 0.7 else "")
        a1, a2 = fake.last_name(), fake.last_name()
    nombre_completo = " ".join(x for x in [n1, n2, a1, a2] if x)
    municipio = fijo.get("municipio") or wchoice(MUNICIPIOS)
    email = None
    if edad >= 16 and rng.random() < 0.75:
        email = f"{sin_tildes(n1).lower()}.{sin_tildes(a1).lower()}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.es'])}"
        email = email.replace(" ", "")

    afil = fijo.get("afiliacion")
    if afil is None:
        r = rng.random()
        if r < 0.08:
            afil = {"eps": None, "regimen": "Particular", "tipo_afiliado": None, "categoria": None, "estado": "NO_APLICA"}
        elif r < 0.70:
            afil = {"eps": rng.choice(EPS_CONTRIBUTIVO), "regimen": "Contributivo",
                    "tipo_afiliado": "Cotizante" if edad >= 18 and rng.random() < 0.6 else "Beneficiario",
                    "categoria": wchoice({"A": 55, "B": 33, "C": 12}),
                    "estado": wchoice({"ACTIVO": 90, "SUSPENDIDO": 7, "RETIRADO": 3})}
        else:
            afil = {"eps": rng.choice(EPS_SUBSIDIADO), "regimen": "Subsidiado", "tipo_afiliado": "Cabeza de familia" if edad >= 18 else "Beneficiario",
                    "categoria": wchoice({"Sisben A/B": 75, "Sisben C": 25}),
                    "estado": wchoice({"ACTIVO": 93, "SUSPENDIDO": 4, "RETIRADO": 3})}
    afil["fecha_ultima_validacion"] = iso(dia_habil_pasado(20))

    empresa = fijo.get("empresa")
    if not empresa:
        if edad < 18:
            empresa = "Estudiante / No Aplica"
        elif afil.get("regimen") == "Subsidiado":
            empresa = rng.choice(["Independiente / Informal", "Alcaldía Mayor de Tunja", "Coflonorte / Libertadores S.A.", "Agrícola Boyacá"])
        else:
            empresa = rng.choice(EMPRESAS_COLOMBIA)

    tel = fijo.get("telefono") or telefono()
    paciente = {
        "id_paciente": nuevo_id("ATH-PAC-"),
        "tipo_documento": tipo,
        "numero_documento": num,
        "primer_nombre": n1, "segundo_nombre": n2 or None,
        "primer_apellido": a1, "segundo_apellido": a2,
        "nombre_completo": nombre_completo,
        "fecha_nacimiento": iso(fnac),
        "sexo": sexo,
        "telefono": tel,
        "email": email,
        "direccion": f"{rng.choice(['Calle', 'Carrera', 'Diagonal', 'Transversal'])} {rng.randint(1, 80)} # {rng.randint(1, 60)}-{rng.randint(1, 99)}",
        "municipio": municipio,
        "departamento": "Boyaca",
        "afiliacion": afil,
        "empresa": empresa,
        "acepta_whatsapp": rng.random() < 0.85,
    }
    athenea["pacientes"].append(paciente)

    # iMedical tiene su propia copia del paciente: ~10 % con telefono desactualizado.
    tel_imedical = fijo.get("telefono_imedical") or (tel if rng.random() > 0.10 else telefono())
    antecedentes = fijo.get("antecedentes")
    if antecedentes is None:
        antecedentes = [{"cie10": c, "descripcion": d} for c, d, edad_min in CIE10
                        if edad >= edad_min and rng.random() < (0.22 if edad >= 50 else 0.06)]
    imedical["historias"].append({
        "numero_documento": num,
        "nombre_paciente": nombre_completo,
        "telefono_contacto": tel_imedical,
        "grupo_sanguineo": wchoice(GRUPOS_SANGUINEOS),
        "alergias": fijo.get("alergias") or wchoice(ALERGIAS),
        "antecedentes": antecedentes,
        "ultima_atencion": None,
    })
    return paciente


def especialidad_compatible(p: dict, incluir_lab: bool = True) -> dict:
    edad = edad_en(date.fromisoformat(p["fecha_nacimiento"]))
    opciones = {e["nombre"]: e["peso"] for e in ESPECIALIDADES
                if e["edad"][0] <= edad <= e["edad"][1] and (e["sexo"] in (None, p["sexo"]))
                and (incluir_lab or not e["nombre"].startswith("Toma"))}
    return ESP_BY_NAME[wchoice(opciones)]


def profesional_de(especialidad: str) -> dict:
    return rng.choice([x for x in imedical["profesionales"] if x["especialidad"] == especialidad])


def crear_autorizacion(p: dict, esp: dict, estado: str, emision: date, vigencia_dias: int = 90) -> dict:
    a = {
        "numero_autorizacion": nuevo_id("AUT-2026-"),
        "numero_documento": p["numero_documento"],
        "codigo_cups": esp["cups"],
        "servicio": esp["servicio"],
        "especialidad": esp["nombre"],
        "eps": p["afiliacion"]["eps"],
        "fecha_emision": iso(emision),
        "fecha_vencimiento": iso(emision + timedelta(days=vigencia_dias)),
        "estado": estado,  # VIGENTE (se recalcula a VENCIDA en ejecucion), UTILIZADA, PENDIENTE, NEGADA
    }
    athenea["autorizaciones"].append(a)
    return a


def crear_resultado(p: dict, cita: dict, examenes: list[str] | None = None, estado: str | None = None) -> None:
    toma = date.fromisoformat(cita["fecha_hora"][:10])
    if examenes is None:
        examenes = [x[1] for x in rng.sample(EXAMENES_LAB, rng.randint(1, 4))]
    if estado is None:
        estado = "EN_PROCESO" if (FECHA_ANCLA - toma).days <= 1 else wchoice({"ENTREGADO": 55, "LISTO": 45})
    athenea["resultados"].append({
        "id_orden": nuevo_id("ORD-"),
        "numero_documento": p["numero_documento"],
        "id_cita_toma": cita["id_cita"],
        "examenes": examenes,
        "fecha_toma": cita["fecha_hora"][:10],
        "fecha_estimada_entrega": iso(sumar_habiles(toma, rng.choice([1, 1, 2, 3]))),
        "estado": estado,  # EN_PROCESO | LISTO (disponible para entrega) | ENTREGADO
        "canal_entrega": rng.choice(["Portal web", "Correo electronico", "Presencial"]),
        "sede_toma": cita["sede"],
    })


def crear_cita_pasada(p: dict, esp: dict | None = None, estado: str | None = None,
                      dias_atras: tuple[int, int] = (1, DIAS_HISTORIA)) -> dict:
    esp = esp or especialidad_compatible(p)
    prof = profesional_de(esp["nombre"])
    dia = dia_habil_pasado(dias_atras[1], dias_atras[0])
    inicio, fin = prof["jornada"].split("-")
    hora = rng.choice(horas_bloque(inicio, fin, esp["duracion"]))
    estado = estado or wchoice({"CUMPLIDA": 80, "INASISTENCIA": 10, "CANCELADA": 10})
    aut = None
    if esp["requiere_autorizacion"] and estado == "CUMPLIDA" and p["afiliacion"]["eps"]:
        aut = crear_autorizacion(p, esp, "UTILIZADA", dia - timedelta(days=rng.randint(5, 30)))["numero_autorizacion"]
    cita = {
        "id_cita": nuevo_id("CIT-"),
        "numero_documento": p["numero_documento"],
        "paciente": p["nombre_completo"],
        "id_profesional": prof["id_profesional"],
        "profesional": prof["nombre"],
        "especialidad": esp["nombre"],
        "sede": prof["sede"],
        "fecha_hora": iso_dt(dia, hora),
        "estado": estado,
        "canal_origen": wchoice({"Llamada": 45, "WhatsApp": 35, "Presencial": 18, "Web": 2}),
        "numero_autorizacion": aut,
        "id_slot": None,
    }
    imedical["citas"].append(cita)
    if esp["nombre"].startswith("Toma") and estado == "CUMPLIDA":
        crear_resultado(p, cita)
    return cita


def crear_cita_futura(p: dict, esp: dict | None = None, estado: str | None = None,
                      aut: str | None = None, dia_min: int = 0) -> dict | None:
    esp = esp or especialidad_compatible(p)
    dias = dias_habiles_futuros(DIAS_AGENDA)
    candidatos = [s for s in imedical["agenda"] if s["especialidad"] == esp["nombre"] and s["estado"] == "OCUPADO"
                  and s["id_cita"] is None and s["fecha"] >= iso(dias[dia_min])]
    if not candidatos:
        return None
    slot = rng.choice(candidatos)
    if esp["requiere_autorizacion"] and aut is None and p["afiliacion"]["eps"]:
        aut = crear_autorizacion(p, esp, "VIGENTE", dia_habil_pasado(25, 2))["numero_autorizacion"]
    cita = {
        "id_cita": nuevo_id("CIT-"),
        "numero_documento": p["numero_documento"],
        "paciente": p["nombre_completo"],
        "id_profesional": slot["id_profesional"],
        "profesional": slot["profesional"],
        "especialidad": esp["nombre"],
        "sede": slot["sede"],
        "fecha_hora": iso_dt(date.fromisoformat(slot["fecha"]), slot["hora"]),
        "estado": estado or wchoice({"ASIGNADA": 60, "CONFIRMADA": 40}),
        "canal_origen": wchoice({"Llamada": 45, "WhatsApp": 35, "Presencial": 18, "Web": 2}),
        "numero_autorizacion": aut,
        "id_slot": slot["id_slot"],
    }
    slot["id_cita"] = cita["id_cita"]
    imedical["citas"].append(cita)
    return cita


# --------------------------------------------------------------------------------------
# SAGICC
# --------------------------------------------------------------------------------------
COLAS = {"Agendamiento": 50, "Resultados": 15, "Autorizaciones": 15, "Informacion general": 12, "PQRS": 8}
TIPIFICACIONES = {
    "Agendamiento": {"Asignacion de cita": 50, "Consulta de disponibilidad": 20, "Reprogramacion de cita": 15, "Cancelacion de cita": 15},
    "Resultados": {"Estado de resultados": 80, "Reenvio de resultados": 20},
    "Autorizaciones": {"Estado de autorizacion": 60, "Requisitos de autorizacion": 40},
    "Informacion general": {"Horarios y sedes": 40, "Preparacion de examenes": 35, "Tarifas particulares": 25},
    "PQRS": {"Radicacion PQRS": 70, "Seguimiento PQRS": 30},
}
RESUMENES = {
    "Asignacion de cita": "Usuario solicita cita de {esp}. {extra}",
    "Consulta de disponibilidad": "Usuario consulta disponibilidad para {esp}. Se informa primera fecha disponible.",
    "Reprogramacion de cita": "Usuario solicita reprogramar cita de {esp} por motivos personales.",
    "Cancelacion de cita": "Usuario cancela cita de {esp}.",
    "Estado de resultados": "Usuario pregunta si ya estan listos sus resultados de laboratorio.",
    "Reenvio de resultados": "Usuario solicita reenvio de resultados al correo registrado.",
    "Estado de autorizacion": "Usuario consulta si la autorizacion de {esp} ya fue emitida por su EPS.",
    "Requisitos de autorizacion": "Usuario pregunta requisitos para tramitar autorizacion de {esp}.",
    "Horarios y sedes": "Usuario consulta horarios de atencion y direccion de sedes.",
    "Preparacion de examenes": "Usuario pregunta preparacion para examenes de laboratorio (ayuno).",
    "Tarifas particulares": "Usuario consulta valor particular de consulta/examenes.",
    "Radicacion PQRS": "Usuario manifiesta inconformidad; se radica PQRS.",
    "Seguimiento PQRS": "Usuario solicita seguimiento a PQRS radicada.",
}


def crear_interaccion(p: dict, cuando: datetime, canal: str | None = None, cola: str | None = None,
                      tipificacion: str | None = None, resultado: str | None = None, esp: str | None = None) -> dict:
    canal = canal or wchoice({"WhatsApp": 50, "Voz": 45, "Web chat": 5})
    cola = cola or wchoice(COLAS)
    tipificacion = tipificacion or wchoice(TIPIFICACIONES[cola])
    if canal == "Voz":
        espera = int(rng.lognormvariate(math.log(420), 0.6))
        duracion = int(rng.lognormvariate(math.log(450), 0.35))
        p_abandono = min(0.6, espera / 1800)
    elif canal == "WhatsApp":
        espera = int(rng.lognormvariate(math.log(1500), 0.7))
        duracion = int(rng.lognormvariate(math.log(840), 0.4))
        p_abandono = min(0.35, espera / 7200)
    else:
        espera = int(rng.lognormvariate(math.log(180), 0.5))
        duracion = int(rng.lognormvariate(math.log(420), 0.4))
        p_abandono = 0.08
    if resultado is None:
        resultado = "ABANDONADO" if rng.random() < p_abandono else wchoice({"RESUELTO": 78, "ESCALADO": 12, "PENDIENTE": 10})
    if resultado == "ABANDONADO":
        duracion, consulta, agente = 0, 0, None
    else:
        consulta = int(duracion * rng.uniform(0.35, 0.55))
        agente = rng.choice(AGENTES_SAGICC)
    esp = esp or especialidad_compatible(p, incluir_lab=False)["nombre"]
    extra = {"RESUELTO": "Se asigna cita.", "ESCALADO": "Sin agenda disponible; se escala a coordinacion.",
             "PENDIENTE": "Pendiente verificar autorizacion con la EPS.", "ABANDONADO": ""}[resultado]
    it = {
        "id_interaccion": nuevo_id("SG-INT-"),
        "numero_documento": p["numero_documento"],
        "canal": canal,
        "cola": cola,
        "agente": agente,
        "fecha_inicio": cuando.strftime("%Y-%m-%dT%H:%M:%S"),
        "tiempo_espera_seg": espera,
        "duracion_seg": duracion,
        "tiempo_consulta_sistemas_seg": consulta,
        "tipificacion": tipificacion,
        "resultado": resultado,
        "resumen": ("Usuario abandona antes de ser atendido." if resultado == "ABANDONADO"
                    else RESUMENES[tipificacion].format(esp=esp, extra=extra).strip()),
    }
    sagicc["interacciones"].append(it)
    return it


MOTIVOS_PQRS = {
    "Demora en la atencion telefonica": 26, "No hay agenda disponible para la especialidad": 20,
    "Demora en respuesta por WhatsApp": 18, "La pagina web no permite agendar citas": 8,
    "Demora en entrega de resultados": 10, "Trato del personal": 6, "Cobro de cuota moderadora": 5,
    "Cita cancelada sin previo aviso": 7,
}
AREA_POR_MOTIVO = {
    "Demora en la atencion telefonica": "Contact center", "No hay agenda disponible para la especialidad": "Agendamiento",
    "Demora en respuesta por WhatsApp": "Contact center", "La pagina web no permite agendar citas": "Tecnologia",
    "Demora en entrega de resultados": "Laboratorio", "Trato del personal": "Atencion al usuario",
    "Cobro de cuota moderadora": "Facturacion", "Cita cancelada sin previo aviso": "Agendamiento",
}


def crear_pqrs(p: dict, tipo: str | None = None, motivo: str | None = None, radicacion: date | None = None,
               estado: str | None = None) -> dict:
    tipo = tipo or wchoice({"Queja": 40, "Reclamo": 25, "Peticion": 20, "Sugerencia": 8, "Felicitacion": 7})
    if tipo == "Felicitacion":
        motivo = motivo or "Felicitacion por la atencion recibida"
    motivo = motivo or wchoice(MOTIVOS_PQRS)
    radicacion = radicacion or dia_habil_pasado(60)
    limite = sumar_habiles(radicacion, 15)
    edad_h = habiles_entre(radicacion, FECHA_ANCLA)
    if estado is None:
        if tipo == "Felicitacion":
            estado = "CERRADA"
        elif edad_h > 15:
            estado = wchoice({"CERRADA": 70, "RESPONDIDA": 25, "EN_GESTION": 5})
        elif edad_h > 5:
            estado = wchoice({"RESPONDIDA": 40, "EN_GESTION": 50, "CERRADA": 10})
        else:
            estado = wchoice({"RADICADA": 50, "EN_GESTION": 50})
    respuesta = None
    if estado in ("RESPONDIDA", "CERRADA"):
        respuesta = iso(sumar_habiles(radicacion, rng.randint(2, min(15, max(2, edad_h)))))
    pq = {
        "radicado": nuevo_id("PQRS-2026-", 4),
        "numero_documento": p["numero_documento"],
        "tipo": tipo,
        "motivo": motivo,
        "descripcion": f"{motivo}. Usuario de {p['municipio']} solicita respuesta y solucion.",
        "canal_radicacion": wchoice({"WhatsApp": 35, "Llamada": 25, "Correo electronico": 20, "Buzon presencial": 15, "Web": 5}),
        "fecha_radicacion": iso(radicacion),
        "fecha_limite_respuesta": iso(limite),
        "fecha_respuesta": respuesta,
        "estado": estado,  # RADICADA | EN_GESTION | RESPONDIDA | CERRADA
        "area_responsable": AREA_POR_MOTIVO.get(motivo, "Atencion al usuario"),
    }
    sagicc["pqrs"].append(pq)
    return pq


def momento_laboral(dias_atras_max: int, dia: date | None = None) -> datetime:
    if dia is None:
        while True:
            dia = FECHA_ANCLA - timedelta(days=rng.randint(0, dias_atras_max))
            if dia.weekday() < 5 or (dia.weekday() == 5 and rng.random() < 0.3):
                break
    return datetime(dia.year, dia.month, dia.day, rng.randint(7, 17), rng.randint(0, 59), rng.randint(0, 59))


# --------------------------------------------------------------------------------------
# Pacientes demo (deterministas, usados en pruebas y en la presentacion)
# --------------------------------------------------------------------------------------

def crear_pacientes_demo() -> None:
    # 1. Maria Fernanda: necesita cita de Medicina Interna, tiene autorizacion vigente,
    #    resultados listos, PQRS abierta y telefono inconsistente entre sistemas.
    maria = crear_paciente(
        tipo_documento="CC", numero_documento="1049632145", nombres=("Maria", "Fernanda", "Rojas", "Perez"),
        sexo="F", fecha_nacimiento="1987-05-14", municipio="Tunja", telefono="3104567821",
        telefono_imedical="3157788990", alergias="Penicilina",
        antecedentes=[{"cie10": "E03", "descripcion": "Hipotiroidismo"}],
        afiliacion={"eps": "Nueva EPS", "regimen": "Contributivo", "tipo_afiliado": "Cotizante", "categoria": "B", "estado": "ACTIVO"},
        empresa="Acerías Paz del Río S.A.",
    )
    maria["email"] = "maria.rojas87@gmail.com"
    crear_cita_pasada(maria, ESP_BY_NAME["Medicina General"], "CUMPLIDA", (20, 25))
    toma = crear_cita_pasada(maria, ESP_BY_NAME["Toma de Muestras de Laboratorio"], "CUMPLIDA", (6, 8))
    athenea["resultados"].pop()  # reemplazar resultado aleatorio por uno controlado
    crear_resultado(maria, toma, ["Hemograma completo", "Glucosa en suero", "Colesterol total", "Trigliceridos", "Hormona estimulante de tiroides (TSH)"], "LISTO")
    crear_autorizacion(maria, ESP_BY_NAME["Medicina Interna"], "VIGENTE", FECHA_ANCLA - timedelta(days=9))
    crear_pqrs(maria, "Queja", "Demora en la atencion telefonica", sumar_habiles(FECHA_ANCLA, -4), "EN_GESTION")
    crear_interaccion(maria, momento_laboral(0, sumar_habiles(FECHA_ANCLA, -5)), "Voz", "Agendamiento",
                      "Asignacion de cita", "ABANDONADO", "Medicina Interna")
    crear_interaccion(maria, momento_laboral(0, sumar_habiles(FECHA_ANCLA, -4)), "WhatsApp", "Agendamiento",
                      "Asignacion de cita", "ESCALADO", "Medicina Interna")
    crear_interaccion(maria, momento_laboral(0, sumar_habiles(FECHA_ANCLA, -4)), "Voz", "PQRS",
                      "Radicacion PQRS", "RESUELTO", "Medicina Interna")

    # 2. Jose Antonio: afiliacion SUSPENDIDA, cita de cardiologia confirmada.
    jose = crear_paciente(
        tipo_documento="CC", numero_documento="7175482", nombres=("Jose", "Antonio", "Becerra", "Nino"),
        sexo="M", fecha_nacimiento="1958-02-03", municipio="Duitama", telefono="3118899001",
        antecedentes=[{"cie10": "I10", "descripcion": "Hipertension esencial (primaria)"},
                      {"cie10": "E11", "descripcion": "Diabetes mellitus tipo 2"}],
        afiliacion={"eps": "Salud Total", "regimen": "Contributivo", "tipo_afiliado": "Cotizante", "categoria": "A", "estado": "SUSPENDIDO"},
        empresa="Cementos Argos S.A.",
    )
    crear_cita_pasada(jose, ESP_BY_NAME["Medicina General"], "CUMPLIDA", (30, 40))
    crear_cita_futura(jose, ESP_BY_NAME["Cardiologia"], "CONFIRMADA", dia_min=2)
    crear_interaccion(jose, momento_laboral(0, sumar_habiles(FECHA_ANCLA, -10)), "Voz", "Agendamiento",
                      "Asignacion de cita", "RESUELTO", "Cardiologia")

    # 3. Samuel (menor de edad): resultados en proceso, cita de pediatria asignada.
    samuel = crear_paciente(
        tipo_documento="TI", numero_documento="1052398761", nombres=("Samuel", "David", "Gomez", "Castro"),
        sexo="M", fecha_nacimiento="2014-08-21", municipio="Tunja", telefono="3205551234", antecedentes=[],
        afiliacion={"eps": "Sanitas", "regimen": "Contributivo", "tipo_afiliado": "Beneficiario", "categoria": "A", "estado": "ACTIVO"},
        empresa="Estudiante / No Aplica",
    )
    toma_s = crear_cita_pasada(samuel, ESP_BY_NAME["Toma de Muestras de Laboratorio"], "CUMPLIDA", (1, 1))
    athenea["resultados"].pop()
    crear_resultado(samuel, toma_s, ["Hemograma completo", "Coprologico"], "EN_PROCESO")
    crear_cita_futura(samuel, ESP_BY_NAME["Pediatria"], "ASIGNADA", dia_min=1)

    # 4. Luz Marina: subsidiado, autorizacion de ortopedia VENCIDA, PQRS respondida.
    luz = crear_paciente(
        tipo_documento="CC", numero_documento="23556789", nombres=("Luz", "Marina", "Pinzon", "Avella"),
        sexo="F", fecha_nacimiento="1965-11-30", municipio="Sogamoso", telefono="3132224466",
        empresa="Postobón S.A.",
        antecedentes=[{"cie10": "M54", "descripcion": "Dorsalgia"}],
        afiliacion={"eps": "Coosalud", "regimen": "Subsidiado", "tipo_afiliado": "Cabeza de familia", "categoria": "Sisben A/B", "estado": "ACTIVO"},
    )
    crear_autorizacion(luz, ESP_BY_NAME["Ortopedia y Traumatologia"], "VIGENTE", FECHA_ANCLA - timedelta(days=120))
    crear_pqrs(luz, "Reclamo", "No hay agenda disponible para la especialidad", sumar_habiles(FECHA_ANCLA, -20), "RESPONDIDA")

    # 5. Andres Felipe: paciente particular (sin EPS).
    andres = crear_paciente(
        tipo_documento="CC", numero_documento="1002456789", nombres=("Andres", "Felipe", "Sandoval", "Mora"),
        sexo="M", fecha_nacimiento="1995-03-09", municipio="Paipa", telefono="3016667788", antecedentes=[],
        afiliacion={"eps": None, "regimen": "Particular", "tipo_afiliado": None, "categoria": None, "estado": "NO_APLICA"},
    )
    crear_interaccion(andres, momento_laboral(0, sumar_habiles(FECHA_ANCLA, -2)), "WhatsApp", "Informacion general",
                      "Tarifas particulares", "RESUELTO", "Medicina General")


# --------------------------------------------------------------------------------------
# Generacion masiva
# --------------------------------------------------------------------------------------

def generar_pacientes_aleatorios() -> None:
    for _ in range(N_PACIENTES - len(athenea["pacientes"])):
        p = crear_paciente()
        for _ in range(wchoice({0: 30, 1: 35, 2: 22, 3: 13})):
            crear_cita_pasada(p)
        if rng.random() < 0.30:
            crear_cita_futura(p)
        if rng.random() < 0.25 and p["afiliacion"]["eps"]:
            esp = especialidad_compatible(p, incluir_lab=False)
            if esp["requiere_autorizacion"]:
                estado = wchoice({"VIGENTE": 60, "PENDIENTE": 25, "NEGADA": 5, "VENCIDA": 10})
                emision = FECHA_ANCLA - timedelta(days=rng.randint(100, 150) if estado == "VENCIDA" else rng.randint(1, 40))
                crear_autorizacion(p, esp, "VIGENTE" if estado == "VENCIDA" else estado, emision)


def completar_ultima_atencion() -> None:
    hist = {h["numero_documento"]: h for h in imedical["historias"]}
    for c in imedical["citas"]:
        if c["estado"] == "CUMPLIDA":
            h = hist[c["numero_documento"]]
            if h["ultima_atencion"] is None or c["fecha_hora"] > h["ultima_atencion"]:
                h["ultima_atencion"] = c["fecha_hora"]


def generar_sagicc() -> None:
    sagicc["agentes"] = [{"id_agente": f"AG-{i + 1:02d}", "nombre": n,
                          "colas": rng.sample(list(COLAS), 3), "estado": rng.choice(["Disponible", "En llamada", "Pausa"])}
                         for i, n in enumerate(AGENTES_SAGICC)]
    pacientes = athenea["pacientes"]
    while len(sagicc["interacciones"]) < N_INTERACCIONES:
        crear_interaccion(rng.choice(pacientes), momento_laboral(DIAS_INTERACCIONES))
    while len(sagicc["pqrs"]) < N_PQRS:
        crear_pqrs(rng.choice(pacientes))
    sagicc["interacciones"].sort(key=lambda x: x["fecha_inicio"])


def main() -> None:
    generar_catalogos()
    generar_agenda()
    generar_tarifas()
    crear_pacientes_demo()
    generar_pacientes_aleatorios()
    completar_ultima_atencion()
    generar_sagicc()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"fecha_ancla": iso(FECHA_ANCLA), "semilla": SEED,
            "nota": "Datos 100% ficticios generados para el MVP Copiloto IPS Carvajal."}
    for nombre, contenido in (("athenea", athenea), ("imedical", imedical), ("sagicc", sagicc)):
        ruta = OUT_DIR / f"{nombre}.json"
        ruta.write_text(json.dumps({"meta": meta, **contenido}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"[ok] {ruta.name}: " + ", ".join(f"{k}={len(v)}" for k, v in contenido.items() if isinstance(v, list))
              + f" ({ruta.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
