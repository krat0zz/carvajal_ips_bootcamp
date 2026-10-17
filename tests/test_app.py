"""
Pruebas de integración del MVP Copiloto IPS Carvajal.
Verifica:
  - Funcionamiento de las APIs simuladas (Athenea, iMedical, SAGICC)
  - Validación de header x-api-key
  - Agendamiento y consulta de cupos
  - Orquestador del Copiloto y Ficha 360
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_athenea_autenticacion_requerida():
    # Sin API key debe retornar 401
    resp = client.get("/mock/athenea/api/v1/pacientes/1049632145")
    assert resp.status_code == 401

def test_athenea_consultar_paciente_con_key():
    # Con API key correcta debe retornar 200 y datos de María Fernanda
    resp = client.get("/mock/athenea/api/v1/pacientes/1049632145", headers={"x-api-key": "athenea-dev-key"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["nombre_completo"] == "Maria Fernanda Rojas Perez"
    assert data["afiliacion"]["eps"] == "Nueva EPS"

def test_athenea_resultados_laboratorio():
    # Consultar resultados de laboratorio de María Fernanda
    resp = client.get("/mock/athenea/api/v1/laboratorio/resultados?numero_documento=1049632145", headers={"x-api-key": "athenea-dev-key"})
    assert resp.status_code == 200
    res = resp.json()["data"]
    assert len(res) > 0
    assert "TSH" in str(res[0]["examenes"]) or "Hemograma" in str(res[0]["examenes"])

def test_imedical_disponibilidad():
    # Consultar cupos libres de agenda
    resp = client.get("/mock/imedical/api/v2/agenda/disponibilidad?especialidad=Medicina%20Interna", headers={"x-api-key": "imedical-dev-key"})
    assert resp.status_code == 200
    res = resp.json()["resultado"]
    assert len(res) > 0

def test_sagicc_pqrs():
    # Consultar PQRS de María Fernanda
    resp = client.get("/mock/sagicc/api/v1/pqrs?numero_documento=1049632145", headers={"x-api-key": "sagicc-dev-key"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) > 0

def test_ficha_360_endpoint():
    # Consulta unificada en paralelo
    resp = client.get("/api/patient-360/1049632145")
    assert resp.status_code == 200
    d = resp.json()
    assert "athenea" in d
    assert "imedical" in d
    assert "sagicc" in d
    assert d["athenea"]["paciente"]["nombre_completo"] == "Maria Fernanda Rojas Perez"

def test_chat_copiloto():
    # Prueba del orquestador de chat
    resp = client.post("/api/chat", json={
        "message": "Paciente CC 1049632145 consulta estado de sus laboratorios",
        "history": []
    })
    assert resp.status_code == 200
    d = resp.json()
    assert "respuesta" in d
    assert "trazas" in d
    assert len(d["trazas"]) > 0

def test_liberar_cupo_y_cancelar_cita():
    # 1. Agendar cita en un slot disponible
    resp_disp = client.get("/api/self-service/disponibilidad?especialidad=Medicina%20General")
    assert resp_disp.status_code == 200
    cupos = resp_disp.json().get("resultado", [])
    if cupos:
        slot_id = cupos[0]["id_slot"]
        # Agendar
        resp_ag = client.post("/api/self-service/reservar", json={
            "numero_documento": "1049632145",
            "id_slot": slot_id,
            "canal_origen": "Web autoservicio"
        })
        assert resp_ag.status_code in (200, 201)
        
        # 2. Cancelar / liberar por id_slot vía endpoint público de autoservicio
        resp_lib = client.post("/api/self-service/cancel", json={
            "id_slot": slot_id,
            "motivo": "Cancelacion de prueba por slot"
        })
        assert resp_lib.status_code == 200
        assert resp_lib.json()["resultado"]["estado_cupo"] == "DISPONIBLE"
        
        # 3. Agendar nuevamente y liberar por documento de paciente CC
        resp_ag2 = client.post("/api/self-service/reservar", json={
            "numero_documento": "1049632145",
            "id_slot": slot_id,
            "canal_origen": "Web autoservicio"
        })
        assert resp_ag2.status_code in (200, 201)

        resp_lib2 = client.post("/api/self-service/cancel", json={
            "numero_documento": "1049632145",
            "motivo": "Cancelacion de prueba por CC"
        })
        assert resp_lib2.status_code == 200
        assert resp_lib2.json()["resultado"]["estado_cupo"] == "DISPONIBLE"


def test_registrar_y_actualizar_paciente():
    # 1. Registrar nuevo paciente con documento único
    import time
    nuevo_doc = f"99{int(time.time() * 1000) % 100000000:08d}"
    resp_reg = client.post("/api/patients", json={
        "tipo_documento": "CC",
        "numero_documento": nuevo_doc,
        "primer_nombre": "Carlos",
        "primer_apellido": "Guerra",
        "fecha_nacimiento": "1994-04-12",
        "telefono": "3114445566",
        "email": "carlos.guerra@test.com",
        "empresa": "Acerías Paz del Río S.A."
    })
    assert resp_reg.status_code in (200, 201)
    data = resp_reg.json().get("data", {})
    assert data["numero_documento"] == nuevo_doc
    assert data["nombre_completo"] == "Carlos Guerra"

    # 2. Actualizar datos de contacto y empresa
    resp_act = client.patch(f"/api/patients/{nuevo_doc}", json={
        "telefono": "3159998877",
        "empresa": "Cementos Argos S.A."
    })
    assert resp_act.status_code == 200
    data_act = resp_act.json().get("data", {})
    assert data_act["telefono"] == "3159998877"
    assert data_act["empresa"] == "Cementos Argos S.A."

    # 3. Validar reflejo en Ficha 360
    resp_360 = client.get(f"/api/patient-360/{nuevo_doc}")
    assert resp_360.status_code == 200
    p = resp_360.json()["athenea"]["paciente"]
    assert p["telefono"] == "3159998877"
    assert p["empresa"] == "Cementos Argos S.A."


def test_chat_copiloto_actualizar_datos():
    # Probar que el copiloto ejecuta la tool actualizar_datos_paciente
    resp = client.post("/api/chat", json={
        "message": "Actualizar teléfono a 3108887766 para el paciente con cédula 1049632145",
        "history": []
    })
    assert resp.status_code == 200
    d = resp.json()
    assert "respuesta" in d
    assert any(t.get("tool") == "actualizar_datos_paciente" for t in d.get("trazas", []))


def test_swagger_mocks_docs_y_openapi():
    # Validar que /mock/docs y /mock/openapi.json carguen sin errores 500
    resp_docs = client.get("/mock/docs")
    assert resp_docs.status_code == 200

    resp_openapi = client.get("/mock/openapi.json")
    assert resp_openapi.status_code == 200
    data = resp_openapi.json()
    assert "paths" in data
    assert "/athenea/api/v1/pacientes/{numero_documento}" in data["paths"]
    assert "/imedical/api/v2/agenda/liberar" in data["paths"]

