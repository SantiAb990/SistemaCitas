"""
Pruebas funcionales automáticas (usan el cliente de pruebas de Flask).
Requisitos: MySQL encendido y schema.sql ya cargado.
Ejecutar desde la carpeta del proyecto:   python tests/pruebas_funcionales.py
"""
import os, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import app, query

app.config["TESTING"] = True
RESULTADOS = []


def check(codigo, descripcion, condicion):
    RESULTADOS.append((codigo, descripcion, bool(condicion)))
    print(f"[{'OK ' if condicion else 'FALLA'}] {codigo}: {descripcion}")


def cliente(correo=None, password=None):
    c = app.test_client()
    if correo:
        c.post("/login", data={"correo": correo, "password": password})
    return c


def texto(resp):
    return resp.get_data(as_text=True)


manana = (date.today() + timedelta(days=20)).isoformat()
ayer = (date.today() - timedelta(days=1)).isoformat()

# ---------- Autenticación ----------
c = cliente()
check("P01", "Ruta protegida redirige al login sin sesión", c.get("/dashboard").status_code == 302)
r = c.post("/login", data={"correo": "admin@citas.com", "password": "mala"}, follow_redirects=True)
check("P02", "Login con contraseña incorrecta muestra error", "incorrectos" in texto(r))
r = c.post("/login", data={"correo": "admin@citas.com", "password": "Admin123"}, follow_redirects=True)
check("P03", "Login correcto entra al dashboard", "Panel de administrador" in texto(r))
check("P04", "Logout cierra la sesión", c.get("/logout", follow_redirects=True).status_code == 200
      and c.get("/dashboard").status_code == 302)

# ---------- Control de acceso por rol ----------
pac = cliente("paciente@citas.com", "Paciente123")
check("P05", "Paciente NO puede ver /usuarios (403)", pac.get("/usuarios").status_code == 403)
check("P06", "Paciente NO puede ver /pacientes (403)", pac.get("/pacientes").status_code == 403)
check("P07", "Paciente NO puede ver /reportes (403)", pac.get("/reportes").status_code == 403)
rec = cliente("recepcion@citas.com", "Recep123")
check("P08", "Recepcionista NO puede ver /usuarios (403)", rec.get("/usuarios").status_code == 403)
check("P09", "Recepcionista SÍ puede ver /reportes", rec.get("/reportes").status_code == 200)
med = cliente("medico@citas.com", "Medico123")
check("P10", "Médico NO puede crear pacientes (403)", med.get("/pacientes/nuevo").status_code == 403)
check("P11", "Médico SÍ ve el listado de pacientes", med.get("/pacientes").status_code == 200)
adm = cliente("admin@citas.com", "Admin123")
check("P12", "Administrador ve /usuarios", adm.get("/usuarios").status_code == 200)

# ---------- CRUD pacientes ----------
r = rec.post("/pacientes/nuevo", data={"nombre": "Paciente Prueba", "documento": "99887766",
             "correo": "prueba@correo.com", "telefono": "3001234567"}, follow_redirects=True)
check("P13", "Crear paciente (CREATE)", "Paciente creado" in texto(r))
pid = query("SELECT id FROM pacientes WHERE documento='99887766'", one=True)["id"]
r = rec.post("/pacientes/nuevo", data={"nombre": "Otro", "documento": "99887766",
             "correo": "otro@correo.com"}, follow_redirects=True)
check("P14", "Documento duplicado es rechazado", "ya existe" in texto(r).lower())
r = rec.post("/pacientes/nuevo", data={"nombre": "Ab", "documento": "12ab", "correo": "mal"})
check("P15", "Validación de formulario (nombre, documento, correo)",
      "al menos 3 caracteres" in texto(r) and "entre 5 y 15 dígitos" in texto(r) and "formato válido" in texto(r))
check("P16", "Consultar paciente (READ)", "Paciente Prueba" in texto(rec.get("/pacientes?q=Prueba")))
r = rec.post(f"/pacientes/{pid}/editar", data={"nombre": "Paciente Editado", "documento": "99887766",
             "correo": "prueba@correo.com", "telefono": "3001234567"}, follow_redirects=True)
check("P17", "Actualizar paciente (UPDATE)", "actualizado" in texto(r) and "Paciente Editado" in texto(r))

# ---------- Citas ----------
datos_cita = {"paciente_id": pid, "medico_id": 1, "fecha": manana, "hora": "10:00", "motivo": "Control de prueba"}
r = rec.post("/citas/nueva", data=datos_cita, follow_redirects=True)
check("P18", "Agendar cita (CREATE)", "agendada" in texto(r))
cid = query("SELECT id FROM citas WHERE paciente_id=%s", (pid,), one=True)["id"]
r = rec.post("/citas/nueva", data=dict(datos_cita, paciente_id=2), follow_redirects=True)
check("P19", "No permite dos citas del mismo médico en el mismo horario", "ya tiene una cita" in texto(r))
r = rec.post("/citas/nueva", data=dict(datos_cita, fecha=ayer, hora="11:00"))
check("P20", "No permite fechas pasadas", "anterior a hoy" in texto(r))
r = rec.post("/citas/nueva", data=dict(datos_cita, hora="23:00", motivo="x"))
check("P21", "Valida hora y motivo", "hora válida" in texto(r) and "motivo" in texto(r).lower())
r = rec.post(f"/citas/{cid}/editar", data=dict(datos_cita, hora="11:30"), follow_redirects=True)
check("P22", "Reprogramar cita (UPDATE)", "reprogramada" in texto(r))
r = rec.post(f"/citas/{cid}/estado", data={"estado": "Confirmada"}, follow_redirects=True)
check("P23", "Confirmar cita", "confirmada" in texto(r))
r = pac.post(f"/citas/{cid}/estado", data={"estado": "Cancelada"}, follow_redirects=True)
check("P24", "Paciente NO puede cancelar la cita de otro", "No tienes permiso" in texto(r))

# Paciente demo agenda su propia cita
r = pac.post("/citas/nueva", data={"medico_id": 2, "fecha": manana, "hora": "09:00",
             "motivo": "Dolor de espalda"}, follow_redirects=True)
check("P25", "Paciente agenda su propia cita", "agendada" in texto(r))
mid = query("SELECT id FROM citas WHERE motivo='Dolor de espalda'", one=True)["id"]
r = pac.post(f"/citas/{mid}/estado", data={"estado": "Cancelada"}, follow_redirects=True)
check("P26", "Paciente cancela su propia cita", "cancelada" in texto(r))
check("P27", "Paciente solo ve sus citas", "Gripa y fiebre" not in texto(pac.get("/citas")))

# ---------- Médico: atención e historial ----------
r = med.get(f"/citas/{cid}/atender")
check("P28", "Médico abre el formulario de atención", r.status_code == 200 and "Registro clínico" in texto(r))
r = med.post(f"/citas/{cid}/atender", data={"diagnostico": "abc"}, follow_redirects=True)
check("P29", "Diagnóstico muy corto es rechazado", "al menos 5 caracteres" in texto(r))
r = med.post(f"/citas/{cid}/atender", data={"diagnostico": "Resfriado común",
             "tratamiento": "Reposo", "observaciones": "Control en 7 días"}, follow_redirects=True)
check("P30", "Registrar atención e historial", "Atención registrada" in texto(r))
check("P31", "La cita queda como Atendida",
      query("SELECT estado FROM citas WHERE id=%s", (cid,), one=True)["estado"] == "Atendida")
check("P32", "Historial visible para el médico", "Resfriado común" in texto(med.get(f"/pacientes/{pid}/historial")))
check("P33", "Paciente NO ve historial de otro (403)", pac.get(f"/pacientes/{pid}/historial").status_code == 403)
check("P34", "Paciente ve su propio historial", "Chequeo anual" in texto(pac.get("/mi-historial", follow_redirects=True)))
otra = cliente("ana.torres@citas.com", "Medico123")
check("P35", "Médico no atiende citas de otro médico", "no encontrada" in texto(otra.get(f"/citas/{cid}/atender", follow_redirects=True)))

# ---------- Dashboard, reportes, administración ----------
for nombre, cl in (("administrador", adm), ("recepcionista", rec), ("médico", med), ("paciente", pac)):
    r = cl.get("/dashboard")
    check("P36", f"Dashboard de {nombre} carga con indicadores", r.status_code == 200 and "valor" in texto(r))
r = rec.get("/reportes")
check("P37", "Reporte de citas con filtros", r.status_code == 200 and "Por médico" in texto(r))
r = rec.get(f"/reportes?estado=Atendida&desde={ayer}&hasta={manana}")
check("P38", "Reporte filtrado por estado", "Resfriado" in texto(r) or "Control de prueba" in texto(r))
r = rec.get("/reportes/csv")
check("P39", "Exportar reporte a CSV", r.mimetype == "text/csv" and "Paciente" in texto(r))

r = adm.post("/medicos/nuevo", data={"nombre": "Dr. Prueba", "correo": "drprueba@citas.com",
             "especialidad_id": 3, "telefono": "3001112222", "registro_profesional": "RM-9999",
             "password": "Clave123"}, follow_redirects=True)
check("P40", "Admin crea médico (usuario + perfil)", "guardado" in texto(r))
check("P41", "El nuevo médico puede iniciar sesión",
      "Panel de medico" in texto(cliente().post("/login", data={"correo": "drprueba@citas.com",
      "password": "Clave123"}, follow_redirects=True)))
mnuevo = query("SELECT id FROM medicos WHERE registro_profesional='RM-9999'", one=True)["id"]
r = adm.post(f"/medicos/{mnuevo}/eliminar", follow_redirects=True)
check("P42", "Admin elimina médico sin citas", "Médico eliminado" in texto(r))
r = adm.post("/medicos/1/eliminar", follow_redirects=True)
check("P43", "No se elimina un médico con citas (integridad)", "tiene citas" in texto(r))
r = adm.post("/especialidades", data={"nombre": "Neurología"}, follow_redirects=True)
check("P44", "Admin crea especialidad", "Neurología" in texto(r))
r = adm.post("/usuarios/nuevo", data={"nombre": "Recep Dos", "correo": "recep2@citas.com",
             "rol": "recepcionista", "password": "Clave123"}, follow_redirects=True)
check("P45", "Admin crea recepcionista", "Usuario creado" in texto(r))
r = cliente().post("/registro", data={"nombre": "Nuevo Paciente", "documento": "55443322",
             "correo": "nuevo@correo.com", "password": "Clave123", "confirmar": "Clave123"}, follow_redirects=True)
check("P46", "Auto-registro de paciente", "Registro exitoso" in texto(r))
r = cliente().post("/registro", data={"nombre": "Nuevo Paciente", "documento": "55443399",
             "correo": "nuevo@correo.com", "password": "Clave123", "confirmar": "Clave123"})
check("P47", "Registro con correo repetido es rechazado", "ya existe" in texto(r).lower())

# ---------- Eliminar (DELETE) y limpieza ----------
r = rec.post(f"/pacientes/{pid}/eliminar", follow_redirects=True)
check("P48", "Eliminar paciente (DELETE) y sus citas en cascada",
      "eliminado" in texto(r) and query("SELECT COUNT(*) n FROM citas WHERE paciente_id=%s", (pid,), one=True)["n"] == 0)

fallas = [x for x in RESULTADOS if not x[2]]
print(f"\nResultado: {len(RESULTADOS) - len(fallas)}/{len(RESULTADOS)} pruebas correctas")
sys.exit(1 if fallas else 0)
