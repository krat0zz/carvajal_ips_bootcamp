"""
Genera los archivos SQL divididos para Supabase, evitando el límite de tamaño del SQL Editor web:
  - data/supabase_01_schema.sql (~10 KB) -> Tablas, indices y RLS (corre en 1 segundo).
  - data/supabase_02_athenea.sql (~300 KB) -> Datos de Athenea (laboratorios, pacientes, autorizaciones, tarifas).
  - data/supabase_03_imedical.sql (~650 KB) -> Datos de iMedical (sedes, agenda, citas, historia).
  - data/supabase_04_sagicc.sql (~400 KB) -> Datos de SAGICC (agentes, interacciones, PQRS).

Uso:
  .\\.venv\\Scripts\\python.exe data/export_to_sql.py
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "generated"
OUT_DIR = Path(__file__).resolve().parent

def esc(val):
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (dict, list)):
        texto = json.dumps(val, ensure_ascii=False)
        return "'" + texto.replace("'", "''") + "'::jsonb"
    texto = str(val).replace("'", "''")
    return f"'{texto}'"

def batch_insert(tabla, columnas, filas, batch_size=150):
    if not filas:
        return []
    lines = [f"-- Insertando en {tabla} ({len(filas)} filas)"]
    cols_str = ", ".join(columnas)
    for i in range(0, len(filas), batch_size):
        lote = filas[i:i + batch_size]
        vals_sql = []
        for item in lote:
            row_vals = [esc(item.get(c)) for c in columnas]
            vals_sql.append(f"({', '.join(row_vals)})")
        lines.append(f"INSERT INTO {tabla} ({cols_str}) VALUES\n" + ",\n".join(vals_sql) + "\nON CONFLICT DO NOTHING;\n")
    return lines

def main():
    athenea = json.loads((DATA_DIR / "athenea.json").read_text(encoding="utf-8"))
    imedical = json.loads((DATA_DIR / "imedical.json").read_text(encoding="utf-8"))
    sagicc = json.loads((DATA_DIR / "sagicc.json").read_text(encoding="utf-8"))

    # 1. SCHEMA
    schema_sql = [
        "-- ==========================================================================",
        "-- PARTE 1: TABLAS, ÍNDICES Y POLÍTICAS RLS (IPS CARVAJAL)",
        "-- ==========================================================================\n",
        "BEGIN;\n",
        """
CREATE TABLE IF NOT EXISTS athenea_pacientes (
    id_paciente TEXT PRIMARY KEY,
    tipo_documento TEXT NOT NULL,
    numero_documento TEXT UNIQUE NOT NULL,
    primer_nombre TEXT NOT NULL,
    segundo_nombre TEXT,
    primer_apellido TEXT NOT NULL,
    segundo_apellido TEXT,
    nombre_completo TEXT NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    sexo CHAR(1),
    telefono TEXT,
    email TEXT,
    direccion TEXT,
    municipio TEXT,
    departamento TEXT,
    afiliacion JSONB,
    acepta_whatsapp BOOLEAN DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_ath_pac_doc ON athenea_pacientes(numero_documento);

CREATE TABLE IF NOT EXISTS athenea_autorizaciones (
    numero_autorizacion TEXT PRIMARY KEY,
    numero_documento TEXT NOT NULL,
    codigo_cups TEXT,
    servicio TEXT,
    especialidad TEXT,
    eps TEXT,
    fecha_emision DATE,
    fecha_vencimiento DATE,
    estado TEXT
);
CREATE INDEX IF NOT EXISTS idx_ath_aut_doc ON athenea_autorizaciones(numero_documento);

CREATE TABLE IF NOT EXISTS athenea_tarifas (
    id SERIAL PRIMARY KEY,
    codigo_cups TEXT,
    servicio TEXT,
    entidad TEXT,
    valor NUMERIC,
    moneda TEXT,
    tipo TEXT
);

CREATE TABLE IF NOT EXISTS athenea_cuotas_moderadoras (
    id SERIAL PRIMARY KEY,
    regimen TEXT,
    categoria TEXT,
    cuota_moderadora NUMERIC,
    copago_porcentaje NUMERIC,
    nota TEXT
);

CREATE TABLE IF NOT EXISTS athenea_examenes_laboratorio (
    codigo_cups TEXT PRIMARY KEY,
    examen TEXT NOT NULL,
    valor_particular NUMERIC
);

CREATE TABLE IF NOT EXISTS athenea_resultados (
    id_orden TEXT PRIMARY KEY,
    numero_documento TEXT NOT NULL,
    id_cita_toma TEXT,
    examenes JSONB,
    fecha_toma DATE,
    fecha_estimada_entrega DATE,
    estado TEXT,
    canal_entrega TEXT,
    sede_toma TEXT
);
CREATE INDEX IF NOT EXISTS idx_ath_res_doc ON athenea_resultados(numero_documento);

CREATE TABLE IF NOT EXISTS imedical_sedes (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    direccion TEXT,
    telefono TEXT,
    horario TEXT
);

CREATE TABLE IF NOT EXISTS imedical_especialidades (
    especialidad TEXT PRIMARY KEY,
    codigo_cups TEXT,
    servicio TEXT,
    duracion_min INT,
    sedes JSONB,
    requiere_autorizacion BOOLEAN,
    restriccion_edad JSONB,
    restriccion_sexo TEXT
);

CREATE TABLE IF NOT EXISTS imedical_profesionales (
    id_profesional TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    especialidad TEXT NOT NULL,
    sede TEXT,
    registro_medico TEXT,
    jornada TEXT
);

CREATE TABLE IF NOT EXISTS imedical_agenda (
    id_slot TEXT PRIMARY KEY,
    id_profesional TEXT,
    profesional TEXT,
    especialidad TEXT,
    sede TEXT,
    fecha DATE,
    hora TEXT,
    duracion_min INT,
    estado TEXT,
    id_cita TEXT
);
CREATE INDEX IF NOT EXISTS idx_im_agenda_filtro ON imedical_agenda(especialidad, estado, fecha);

CREATE TABLE IF NOT EXISTS imedical_citas (
    id_cita TEXT PRIMARY KEY,
    numero_documento TEXT NOT NULL,
    paciente TEXT,
    id_profesional TEXT,
    profesional TEXT,
    especialidad TEXT,
    sede TEXT,
    fecha_hora TIMESTAMP,
    estado TEXT,
    canal_origen TEXT,
    numero_autorizacion TEXT,
    id_slot TEXT
);
CREATE INDEX IF NOT EXISTS idx_im_citas_doc ON imedical_citas(numero_documento);

CREATE TABLE IF NOT EXISTS imedical_historias (
    numero_documento TEXT PRIMARY KEY,
    nombre_paciente TEXT,
    telefono_contacto TEXT,
    grupo_sanguineo TEXT,
    alergias TEXT,
    antecedentes JSONB,
    ultima_atencion TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sagicc_agentes (
    id_agente TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    colas JSONB,
    estado TEXT
);

CREATE TABLE IF NOT EXISTS sagicc_interacciones (
    id_interaccion TEXT PRIMARY KEY,
    numero_documento TEXT NOT NULL,
    canal TEXT,
    cola TEXT,
    agente TEXT,
    fecha_inicio TIMESTAMP,
    tiempo_espera_seg INT,
    duracion_seg INT,
    tiempo_consulta_sistemas_seg INT,
    tipificacion TEXT,
    resultado TEXT,
    resumen TEXT
);
CREATE INDEX IF NOT EXISTS idx_sg_int_doc ON sagicc_interacciones(numero_documento);

CREATE TABLE IF NOT EXISTS sagicc_pqrs (
    radicado TEXT PRIMARY KEY,
    numero_documento TEXT NOT NULL,
    tipo TEXT,
    motivo TEXT,
    descripcion TEXT,
    canal_radicacion TEXT,
    fecha_radicacion DATE,
    fecha_limite_respuesta DATE,
    fecha_respuesta DATE,
    estado TEXT,
    area_responsable TEXT
);
CREATE INDEX IF NOT EXISTS idx_sg_pqrs_doc ON sagicc_pqrs(numero_documento);
        """,
        "-- POLÍTICAS ROW LEVEL SECURITY (RLS)",
    ]
    tablas = [
        "athenea_pacientes", "athenea_autorizaciones", "athenea_tarifas", "athenea_cuotas_moderadoras",
        "athenea_examenes_laboratorio", "athenea_resultados", "imedical_sedes", "imedical_especialidades",
        "imedical_profesionales", "imedical_agenda", "imedical_citas", "imedical_historias",
        "sagicc_agentes", "sagicc_interacciones", "sagicc_pqrs"
    ]
    for t in tablas:
        schema_sql.append(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;")
        schema_sql.append(f"DROP POLICY IF EXISTS \"Lectura publica {t}\" ON {t};")
        schema_sql.append(f"CREATE POLICY \"Lectura publica {t}\" ON {t} FOR SELECT USING (true);")
        schema_sql.append(f"DROP POLICY IF EXISTS \"Escritura publica {t}\" ON {t};")
        schema_sql.append(f"CREATE POLICY \"Escritura publica {t}\" ON {t} FOR ALL USING (true) WITH CHECK (true);")
    schema_sql.append("\nCOMMIT;\n")

    f_schema = OUT_DIR / "supabase_01_schema.sql"
    f_schema.write_text("\n".join(schema_sql), encoding="utf-8")
    print(f"[OK] {f_schema.name} ({f_schema.stat().st_size / 1024:.1f} KB)")

    # 2. ATHENEA DATA
    athenea_sql = ["BEGIN;\n"]
    athenea_sql += batch_insert("athenea_pacientes",
             ["id_paciente", "tipo_documento", "numero_documento", "primer_nombre", "segundo_nombre",
              "primer_apellido", "segundo_apellido", "nombre_completo", "fecha_nacimiento", "sexo",
              "telefono", "email", "direccion", "municipio", "departamento", "afiliacion", "acepta_whatsapp"],
             athenea["pacientes"])
    athenea_sql += batch_insert("athenea_autorizaciones",
             ["numero_autorizacion", "numero_documento", "codigo_cups", "servicio", "especialidad", "eps",
              "fecha_emision", "fecha_vencimiento", "estado"],
             athenea["autorizaciones"])
    athenea_sql += batch_insert("athenea_tarifas",
             ["codigo_cups", "servicio", "entidad", "valor", "moneda", "tipo"],
             athenea["tarifas"])
    athenea_sql += batch_insert("athenea_cuotas_moderadoras",
             ["regimen", "categoria", "cuota_moderadora", "copago_porcentaje", "nota"],
             athenea["cuotas_moderadoras"])
    athenea_sql += batch_insert("athenea_examenes_laboratorio",
             ["codigo_cups", "examen", "valor_particular"],
             athenea["examenes_laboratorio"])
    athenea_sql += batch_insert("athenea_resultados",
             ["id_orden", "numero_documento", "id_cita_toma", "examenes", "fecha_toma",
              "fecha_estimada_entrega", "estado", "canal_entrega", "sede_toma"],
             athenea["resultados"])
    athenea_sql.append("\nCOMMIT;\n")
    f_ath = OUT_DIR / "supabase_02_athenea.sql"
    f_ath.write_text("\n".join(athenea_sql), encoding="utf-8")
    print(f"[OK] {f_ath.name} ({f_ath.stat().st_size / 1024:.1f} KB)")

    # 3. IMEDICAL DATA
    imedical_sql = ["BEGIN;\n"]
    imedical_sql += batch_insert("imedical_sedes",
             ["codigo", "nombre", "direccion", "telefono", "horario"],
             imedical["sedes"])
    imedical_sql += batch_insert("imedical_especialidades",
             ["especialidad", "codigo_cups", "servicio", "duracion_min", "sedes", "requiere_autorizacion",
              "restriccion_edad", "restriccion_sexo"],
             imedical["especialidades"])
    imedical_sql += batch_insert("imedical_profesionales",
             ["id_profesional", "nombre", "especialidad", "sede", "registro_medico", "jornada"],
             imedical["profesionales"])
    imedical_sql += batch_insert("imedical_agenda",
             ["id_slot", "id_profesional", "profesional", "especialidad", "sede", "fecha", "hora",
              "duracion_min", "estado", "id_cita"],
             imedical["agenda"])
    imedical_sql += batch_insert("imedical_citas",
             ["id_cita", "numero_documento", "paciente", "id_profesional", "profesional", "especialidad",
              "sede", "fecha_hora", "estado", "canal_origen", "numero_autorizacion", "id_slot"],
             imedical["citas"])
    imedical_sql += batch_insert("imedical_historias",
             ["numero_documento", "nombre_paciente", "telefono_contacto", "grupo_sanguineo", "alergias",
              "antecedentes", "ultima_atencion"],
             imedical["historias"])
    imedical_sql.append("\nCOMMIT;\n")
    f_im = OUT_DIR / "supabase_03_imedical.sql"
    f_im.write_text("\n".join(imedical_sql), encoding="utf-8")
    print(f"[OK] {f_im.name} ({f_im.stat().st_size / 1024:.1f} KB)")

    # 4. SAGICC DATA
    sagicc_sql = ["BEGIN;\n"]
    sagicc_sql += batch_insert("sagicc_agentes",
             ["id_agente", "nombre", "colas", "estado"],
             sagicc["agentes"])
    sagicc_sql += batch_insert("sagicc_interacciones",
             ["id_interaccion", "numero_documento", "canal", "cola", "agente", "fecha_inicio",
              "tiempo_espera_seg", "duracion_seg", "tiempo_consulta_sistemas_seg", "tipificacion",
              "resultado", "resumen"],
             sagicc["interacciones"])
    sagicc_sql += batch_insert("sagicc_pqrs",
             ["radicado", "numero_documento", "tipo", "motivo", "descripcion", "canal_radicacion",
              "fecha_radicacion", "fecha_limite_respuesta", "fecha_respuesta", "estado", "area_responsable"],
             sagicc["pqrs"])
    sagicc_sql.append("\nCOMMIT;\n")
    f_sg = OUT_DIR / "supabase_04_sagicc.sql"
    f_sg.write_text("\n".join(sagicc_sql), encoding="utf-8")
    print(f"[OK] {f_sg.name} ({f_sg.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    main()
