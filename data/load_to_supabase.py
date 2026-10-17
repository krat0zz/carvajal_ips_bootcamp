"""
Cargador de datos a Supabase via API REST (PostgREST).
Lee SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY (o SUPABASE_KEY) desde .env.

Requisito previo:
  Haber ejecutado la seccion de CREATE TABLE de 'data/supabase_schema_and_seed.sql'
  en el SQL Editor de Supabase (o usar el script SQL completo).

Uso:
  .\\.venv\\Scripts\\python.exe data/load_to_supabase.py
"""
import json
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = Path(__file__).resolve().parent / "generated"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/").removesuffix("/rest/v1")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

def cargar_tabla(client: httpx.Client, tabla: str, filas: list[dict], batch_size: int = 150):
    if not filas:
        return
    url = f"{SUPABASE_URL}/rest/v1/{tabla}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }

    print(f"-> Cargando {len(filas)} registros en {tabla}...")
    for i in range(0, len(filas), batch_size):
        lote = filas[i:i + batch_size]
        resp = client.post(url, headers=headers, json=lote)
        if resp.status_code not in (200, 201):
            print(f"   [ERROR en lote {i}-{i+len(lote)}]: {resp.status_code} - {resp.text[:300]}")
            return False
    print(f"   [OK] {tabla} cargada.")
    return True

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[!] ERROR: Debes configurar SUPABASE_URL y SUPABASE_KEY (o SUPABASE_SERVICE_ROLE_KEY) en tu archivo .env")
        print("    Ejemplo en .env:")
        print("    SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co")
        print("    SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI...")
        return

    athenea = json.loads((DATA_DIR / "athenea.json").read_text(encoding="utf-8"))
    imedical = json.loads((DATA_DIR / "imedical.json").read_text(encoding="utf-8"))
    sagicc = json.loads((DATA_DIR / "sagicc.json").read_text(encoding="utf-8"))

    with httpx.Client(timeout=30.0) as client:
        # Athenea
        cargar_tabla(client, "athenea_pacientes", athenea["pacientes"])
        cargar_tabla(client, "athenea_autorizaciones", athenea["autorizaciones"])
        cargar_tabla(client, "athenea_tarifas", athenea["tarifas"])
        cargar_tabla(client, "athenea_cuotas_moderadoras", athenea["cuotas_moderadoras"])
        cargar_tabla(client, "athenea_examenes_laboratorio", athenea["examenes_laboratorio"])
        cargar_tabla(client, "athenea_resultados", athenea["resultados"])

        # iMedical
        cargar_tabla(client, "imedical_sedes", imedical["sedes"])
        cargar_tabla(client, "imedical_especialidades", imedical["especialidades"])
        cargar_tabla(client, "imedical_profesionales", imedical["profesionales"])
        cargar_tabla(client, "imedical_agenda", imedical["agenda"])
        cargar_tabla(client, "imedical_citas", imedical["citas"])
        cargar_tabla(client, "imedical_historias", imedical["historias"])

        # SAGICC
        cargar_tabla(client, "sagicc_agentes", sagicc["agentes"])
        cargar_tabla(client, "sagicc_interacciones", sagicc["interacciones"])
        cargar_tabla(client, "sagicc_pqrs", sagicc["pqrs"])

    print("\n[LISTO] Carga completada en Supabase.")

if __name__ == "__main__":
    main()
