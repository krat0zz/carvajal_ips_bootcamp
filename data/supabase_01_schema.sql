-- ==========================================================================
-- PARTE 1: TABLAS, ÍNDICES Y POLÍTICAS RLS (IPS CARVAJAL)
-- ==========================================================================

BEGIN;


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
        
-- POLÍTICAS ROW LEVEL SECURITY (RLS)
ALTER TABLE athenea_pacientes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica athenea_pacientes" ON athenea_pacientes;
CREATE POLICY "Lectura publica athenea_pacientes" ON athenea_pacientes FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica athenea_pacientes" ON athenea_pacientes;
CREATE POLICY "Escritura publica athenea_pacientes" ON athenea_pacientes FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE athenea_autorizaciones ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica athenea_autorizaciones" ON athenea_autorizaciones;
CREATE POLICY "Lectura publica athenea_autorizaciones" ON athenea_autorizaciones FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica athenea_autorizaciones" ON athenea_autorizaciones;
CREATE POLICY "Escritura publica athenea_autorizaciones" ON athenea_autorizaciones FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE athenea_tarifas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica athenea_tarifas" ON athenea_tarifas;
CREATE POLICY "Lectura publica athenea_tarifas" ON athenea_tarifas FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica athenea_tarifas" ON athenea_tarifas;
CREATE POLICY "Escritura publica athenea_tarifas" ON athenea_tarifas FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE athenea_cuotas_moderadoras ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica athenea_cuotas_moderadoras" ON athenea_cuotas_moderadoras;
CREATE POLICY "Lectura publica athenea_cuotas_moderadoras" ON athenea_cuotas_moderadoras FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica athenea_cuotas_moderadoras" ON athenea_cuotas_moderadoras;
CREATE POLICY "Escritura publica athenea_cuotas_moderadoras" ON athenea_cuotas_moderadoras FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE athenea_examenes_laboratorio ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica athenea_examenes_laboratorio" ON athenea_examenes_laboratorio;
CREATE POLICY "Lectura publica athenea_examenes_laboratorio" ON athenea_examenes_laboratorio FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica athenea_examenes_laboratorio" ON athenea_examenes_laboratorio;
CREATE POLICY "Escritura publica athenea_examenes_laboratorio" ON athenea_examenes_laboratorio FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE athenea_resultados ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica athenea_resultados" ON athenea_resultados;
CREATE POLICY "Lectura publica athenea_resultados" ON athenea_resultados FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica athenea_resultados" ON athenea_resultados;
CREATE POLICY "Escritura publica athenea_resultados" ON athenea_resultados FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE imedical_sedes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica imedical_sedes" ON imedical_sedes;
CREATE POLICY "Lectura publica imedical_sedes" ON imedical_sedes FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica imedical_sedes" ON imedical_sedes;
CREATE POLICY "Escritura publica imedical_sedes" ON imedical_sedes FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE imedical_especialidades ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica imedical_especialidades" ON imedical_especialidades;
CREATE POLICY "Lectura publica imedical_especialidades" ON imedical_especialidades FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica imedical_especialidades" ON imedical_especialidades;
CREATE POLICY "Escritura publica imedical_especialidades" ON imedical_especialidades FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE imedical_profesionales ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica imedical_profesionales" ON imedical_profesionales;
CREATE POLICY "Lectura publica imedical_profesionales" ON imedical_profesionales FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica imedical_profesionales" ON imedical_profesionales;
CREATE POLICY "Escritura publica imedical_profesionales" ON imedical_profesionales FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE imedical_agenda ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica imedical_agenda" ON imedical_agenda;
CREATE POLICY "Lectura publica imedical_agenda" ON imedical_agenda FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica imedical_agenda" ON imedical_agenda;
CREATE POLICY "Escritura publica imedical_agenda" ON imedical_agenda FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE imedical_citas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica imedical_citas" ON imedical_citas;
CREATE POLICY "Lectura publica imedical_citas" ON imedical_citas FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica imedical_citas" ON imedical_citas;
CREATE POLICY "Escritura publica imedical_citas" ON imedical_citas FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE imedical_historias ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica imedical_historias" ON imedical_historias;
CREATE POLICY "Lectura publica imedical_historias" ON imedical_historias FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica imedical_historias" ON imedical_historias;
CREATE POLICY "Escritura publica imedical_historias" ON imedical_historias FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE sagicc_agentes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica sagicc_agentes" ON sagicc_agentes;
CREATE POLICY "Lectura publica sagicc_agentes" ON sagicc_agentes FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica sagicc_agentes" ON sagicc_agentes;
CREATE POLICY "Escritura publica sagicc_agentes" ON sagicc_agentes FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE sagicc_interacciones ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica sagicc_interacciones" ON sagicc_interacciones;
CREATE POLICY "Lectura publica sagicc_interacciones" ON sagicc_interacciones FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica sagicc_interacciones" ON sagicc_interacciones;
CREATE POLICY "Escritura publica sagicc_interacciones" ON sagicc_interacciones FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE sagicc_pqrs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Lectura publica sagicc_pqrs" ON sagicc_pqrs;
CREATE POLICY "Lectura publica sagicc_pqrs" ON sagicc_pqrs FOR SELECT USING (true);
DROP POLICY IF EXISTS "Escritura publica sagicc_pqrs" ON sagicc_pqrs;
CREATE POLICY "Escritura publica sagicc_pqrs" ON sagicc_pqrs FOR ALL USING (true) WITH CHECK (true);

COMMIT;
