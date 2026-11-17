# =====================================================================
# Sistema de Gestión de Citas Médicas  -  Flask + MySQL (XAMPP) + Jinja2
# =====================================================================
import csv
import io
import os
import re
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, time
from functools import wraps

import mysql.connector
from flask import (Flask, Response, flash, redirect, render_template,
                   request, session, url_for, jsonify)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambia-esta-clave-antes-de-publicar")

# ---------------------------------------------------------------------
# 1) Conexión a la base de datos (valores por defecto de XAMPP)
# ---------------------------------------------------------------------
DB_CONFIG = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "sistema_citas"),
)

def get_db_connection():
    """Abre la conexión con MySQL usando los datos definidos en DB_CONFIG. Si cambia el puerto o la clave de XAMPP, se ajusta en esa configuración. Si se elimina, el sistema no podrá consultar ni guardar información."""
    return mysql.connector.connect(**DB_CONFIG)


@contextmanager
def db():
    """Abre conexión + cursor (diccionarios), hace commit al salir y
    rollback si algo falla. Uso: with db() as cur: cur.execute(...)"""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def query(sql, params=(), one=False):
    """SELECT rápido: devuelve una fila (one=True) o una lista de filas."""
    with db() as cur:
        cur.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()


def execute(sql, params=()):
    """INSERT/UPDATE/DELETE rápido. Devuelve el id insertado."""
    with db() as cur:
        cur.execute(sql, params)
        return cur.lastrowid


# ---------------------------------------------------------------------
# 2) Constantes, filtros de plantilla y utilidades
# ---------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HORAS = [f"{h:02d}:{m:02d}" for h in range(8, 18) for m in (0, 30)]  # compatibilidad
DIAS = [(0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"), (4, "Viernes"), (5, "Sábado"), (6, "Domingo")]
DURACION_CITA = 30

def horas_disponibles(medico_id, fecha_txt, excluir_cita=None):
    """Calcula turnos de 30 minutos según la jornada y las citas ocupadas."""
    try:
        fecha_obj = date.fromisoformat(fecha_txt)
    except (TypeError, ValueError):
        return []
    jornada = query("SELECT hora_inicio, hora_fin FROM horarios_medicos WHERE medico_id=%s AND dia_semana=%s AND activo=1", (medico_id, fecha_obj.weekday()), one=True)
    if not jornada:
        return []
    def como_hora(valor):
        if isinstance(valor, timedelta):
            return (datetime.min + valor).time()
        return valor if isinstance(valor, time) else time.fromisoformat(str(valor))
    inicio, fin = como_hora(jornada["hora_inicio"]), como_hora(jornada["hora_fin"])
    ocupadas = query("SELECT hora FROM citas WHERE medico_id=%s AND fecha=%s AND estado<>'Cancelada' AND id<>%s", (medico_id, fecha_obj, excluir_cita or 0))
    ocupadas_set = {filtro_hora(x["hora"]) for x in ocupadas}
    disponibles = []
    actual = datetime.combine(fecha_obj, inicio)
    limite = datetime.combine(fecha_obj, fin)
    while actual + timedelta(minutes=DURACION_CITA) <= limite:
        slot = actual.strftime("%H:%M")
        if slot not in ocupadas_set and (fecha_obj > date.today() or slot > datetime.now().strftime("%H:%M")):
            disponibles.append(slot)
        actual += timedelta(minutes=DURACION_CITA)
    return disponibles


def fechas_disponibles(medico_id, dias=30):
    """Lista fechas futuras con al menos un turno libre para un médico."""
    if not medico_id:
        return []
    resultado = []
    for offset in range(dias + 1):
        fecha_obj = date.today() + timedelta(days=offset)
        horas = horas_disponibles(medico_id, fecha_obj.isoformat())
        if horas:
            resultado.append({"fecha": fecha_obj.isoformat(), "horas": horas,
                              "cantidad": len(horas)})
    return resultado


def horario_semanal(medico_id):
    """Devuelve jornadas ordenadas por día para mostrar en paneles y perfiles."""
    filas = query("SELECT dia_semana, hora_inicio, hora_fin FROM horarios_medicos "
                  "WHERE medico_id=%s AND activo=1 ORDER BY dia_semana", (medico_id,))
    return {f["dia_semana"]: f for f in filas}

ESTADOS = ["Programada", "Confirmada", "Atendida", "Cancelada"]
STAFF = ("administrador", "recepcionista")


@app.template_filter("hora")
def filtro_hora(v):
    """MySQL devuelve TIME como timedelta; lo mostramos como HH:MM."""
    if isinstance(v, timedelta):
        s = int(v.total_seconds())
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}"
    return str(v)[:5] if v else ""


@app.template_filter("fecha")
def filtro_fecha(v):
    """Convierte las fechas al formato día/mes/año."""

    if not v:
        return ""

    # Si ya es una fecha de Python
    if isinstance(v, (date, datetime)):
        return v.strftime("%d/%m/%Y")

    # Si MySQL entrega la fecha como texto
    if isinstance(v, str):
        try:
            fecha_convertida = datetime.strptime(v[:10], "%Y-%m-%d")
            return fecha_convertida.strftime("%d/%m/%Y")
        except ValueError:
            return v

    return str(v)

def dup_message(err):
    """Traduce un error 1062 (valor duplicado) a un mensaje entendible."""
    msg = str(err.msg).lower()
    if "correo" in msg:
        return "Ya existe un registro con ese correo."
    if "documento" in msg:
        return "Ya existe un paciente con ese documento."
    if "registro_profesional" in msg:
        return "Ya existe un médico con ese registro profesional."
    if "nombre" in msg:
        return "Ya existe un registro con ese nombre."
    return "Ya existe un registro con esos datos."


def validar_persona(nombre, correo, telefono="", documento=None, fecha_nac=None):
    errores = []
    if len(nombre) < 3:
        errores.append("El nombre debe tener al menos 3 caracteres.")
    if not EMAIL_RE.match(correo):
        errores.append("El correo no tiene un formato válido.")
    if documento is not None and not re.fullmatch(r"\d{5,15}", documento):
        errores.append("El documento debe tener entre 5 y 15 dígitos.")
    if telefono and not re.fullmatch(r"\d{7,15}", telefono):
        errores.append("El teléfono debe tener entre 7 y 15 dígitos.")
    if fecha_nac:
        try:
            if date.fromisoformat(fecha_nac) > date.today():
                errores.append("La fecha de nacimiento no puede ser futura.")
        except ValueError:
            errores.append("La fecha de nacimiento no es válida.")
    return errores


def flash_errores(errores):
    for e in errores:
        flash(e, "danger")


def to_int(valor):
    return int(valor) if valor and str(valor).isdigit() else None


# ---------------------------------------------------------------------
# 3) Autenticación y control de acceso por rol
# ---------------------------------------------------------------------
def login_required(*roles):
    """@login_required()                 -> cualquier usuario autenticado
       @login_required("administrador")  -> solo esos roles"""
    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Inicia sesión para continuar.", "warning")
                return redirect(url_for("login", next=request.path))
            if roles and session.get("rol") not in roles:
                return render_template("error.html", codigo=403,
                                       mensaje="No tienes permiso para ver esta página."), 403
            return f(*args, **kwargs)
        return wrapper
    return decorador


@app.errorhandler(404)
def no_encontrado(_):
    return render_template("error.html", codigo=404, mensaje="La página no existe."), 404


@app.route("/")
def inicio():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Comprueba el correo y la contraseña, verifica que la cuenta esté activa y guarda el rol en la sesión. Si se modifica mal, los usuarios podrían no iniciar sesión o recibir permisos incorrectos."""
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        u = query("""SELECT u.id, u.nombre, u.password_hash, u.activo, r.nombre AS rol
                     FROM usuarios u JOIN roles r ON r.id = u.rol_id
                     WHERE u.correo = %s""", (correo,), one=True)
        if not u or not check_password_hash(u["password_hash"], password):
            flash("Correo o contraseña incorrectos.", "danger")
            return redirect(url_for("login"))
        if not u["activo"]:
            flash("Tu usuario está desactivado. Contacta al administrador.", "warning")
            return redirect(url_for("login"))

        session.clear()
        session.update(user_id=u["id"], nombre=u["nombre"], rol=u["rol"])
        if u["rol"] == "medico":
            m = query("SELECT id FROM medicos WHERE usuario_id=%s", (u["id"],), one=True)
            session["medico_id"] = m["id"] if m else None
        if u["rol"] == "paciente":
            p = query("SELECT id FROM pacientes WHERE usuario_id=%s", (u["id"],), one=True)
            session["paciente_id"] = p["id"] if p else None

        siguiente = request.args.get("next", "")
        if siguiente.startswith("/") and not siguiente.startswith("//"):
            return redirect(siguiente)
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("login"))


@app.route("/registro", methods=["GET", "POST"])
def registro():
    """Auto-registro: crea un usuario con rol paciente + su ficha de paciente."""
    if request.method == "POST":
        f = request.form
        nombre = f.get("nombre", "").strip()
        correo = f.get("correo", "").strip().lower()
        documento = f.get("documento", "").strip()
        telefono = f.get("telefono", "").strip()
        password = f.get("password", "")
        errores = validar_persona(nombre, correo, telefono, documento)
        if len(password) < 6:
            errores.append("La contraseña debe tener al menos 6 caracteres.")
        if password != f.get("confirmar", ""):
            errores.append("Las contraseñas no coinciden.")
        if errores:
            flash_errores(errores)
            return render_template("registro.html", datos=f)
        try:
            with db() as cur:
                cur.execute("""INSERT INTO usuarios (nombre, correo, password_hash, rol_id)
                               VALUES (%s, %s, %s, (SELECT id FROM roles WHERE nombre='paciente'))""",
                            (nombre, correo, generate_password_hash(password, method="pbkdf2:sha256")))
                cur.execute("""INSERT INTO pacientes (usuario_id, documento, nombre, correo, telefono)
                               VALUES (%s, %s, %s, %s, %s)""",
                            (cur.lastrowid, documento, nombre, correo, telefono or None))
        except mysql.connector.IntegrityError as err:
            flash(dup_message(err) if err.errno == 1062 else "No se pudo registrar.", "danger")
            return render_template("registro.html", datos=f)
        flash("Registro exitoso. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("login"))
    return render_template("registro.html", datos={})


# ---------------------------------------------------------------------
# 4) Dashboard (indicadores según el rol)
# ---------------------------------------------------------------------
@app.route("/dashboard")
@login_required()
def dashboard():
    """Prepara los indicadores y la información principal de cada panel. También carga horarios y fechas disponibles según el rol. Si se quita, la ruta principal no podrá mostrar el resumen del sistema."""
    rol = session["rol"]
    filtro, params = "", ()
    if rol == "medico":
        filtro, params = " WHERE c.medico_id = %s", (session.get("medico_id"),)
    elif rol == "paciente":
        filtro, params = " WHERE c.paciente_id = %s", (session.get("paciente_id"),)

    r = query("""SELECT COUNT(*) AS total,
                        COALESCE(SUM(c.fecha = CURDATE()), 0) AS hoy,
                        COALESCE(SUM(c.estado = 'Programada'), 0) AS programadas,
                        COALESCE(SUM(c.estado = 'Confirmada'), 0) AS confirmadas,
                        COALESCE(SUM(c.estado = 'Atendida'), 0) AS atendidas,
                        COALESCE(SUM(c.estado = 'Cancelada'), 0) AS canceladas
                 FROM citas c""" + filtro, params, one=True)
    stats = {k: int(v) for k, v in r.items()}

    if rol in STAFF:
        stats["pacientes"] = query("SELECT COUNT(*) AS n FROM pacientes", one=True)["n"]
        stats["medicos"] = query("SELECT COUNT(*) AS n FROM medicos", one=True)["n"]

    por_estado = query("SELECT c.estado, COUNT(*) AS total FROM citas c" + filtro +
                       " GROUP BY c.estado", params)
    charts = {"estado": {"labels": [x["estado"] for x in por_estado],
                         "data": [int(x["total"]) for x in por_estado]}}
    if rol in STAFF:
        esp = query("""SELECT COALESCE(e.nombre, 'Sin especialidad') AS nombre, COUNT(*) AS total
                       FROM citas c JOIN medicos m ON m.id = c.medico_id
                       LEFT JOIN especialidades e ON e.id = m.especialidad_id
                       GROUP BY nombre ORDER BY total DESC""")
        charts["especialidad"] = {"labels": [x["nombre"] for x in esp],
                                  "data": [int(x["total"]) for x in esp]}

    cond = (filtro + (" AND " if filtro else " WHERE ") +
            "c.fecha >= CURDATE() AND c.estado IN ('Programada','Confirmada')")
    proximas = query("""SELECT c.id, c.fecha, c.hora, c.estado, c.motivo,
                               p.nombre AS paciente, mu.nombre AS medico
                        FROM citas c JOIN pacientes p ON p.id = c.paciente_id
                        JOIN medicos m ON m.id = c.medico_id
                        JOIN usuarios mu ON mu.id = m.usuario_id""" + cond +
                     " ORDER BY c.fecha, c.hora LIMIT 6", params)
    horario_propio = None
    disponibilidad_propia = []
    horarios_medicos = []
    if rol == "medico":
        horario_propio = horario_semanal(session.get("medico_id"))
        disponibilidad_propia = fechas_disponibles(session.get("medico_id"), 30)
    elif rol == "administrador":
        filas_medicos = query("""SELECT m.id, u.nombre FROM medicos m
                                JOIN usuarios u ON u.id=m.usuario_id
                                WHERE u.activo=1 ORDER BY u.nombre""")
        for item in filas_medicos:
            horarios_medicos.append({"medico": item, "horario": horario_semanal(item["id"]),
                                     "fechas": fechas_disponibles(item["id"], 14)})
    return render_template("dashboard.html", stats=stats, charts=charts, proximas=proximas,
                           horario_propio=horario_propio,
                           disponibilidad_propia=disponibilidad_propia,
                           horarios_medicos=horarios_medicos, dias=DIAS)


# ---------------------------------------------------------------------
# 5) CRUD de pacientes (administrador y recepcionista)
# ---------------------------------------------------------------------
@app.route("/pacientes")
@login_required("administrador", "recepcionista", "medico")
def pacientes_lista():
    q = request.args.get("q", "").strip()
    sql, params = "SELECT * FROM pacientes", ()
    if q:
        sql += " WHERE nombre LIKE %s OR documento LIKE %s"
        params = (f"%{q}%", f"%{q}%")
    return render_template("pacientes_lista.html",
                           pacientes=query(sql + " ORDER BY nombre", params), q=q)


@app.route("/pacientes/nuevo", methods=["GET", "POST"])
@app.route("/pacientes/<int:paciente_id>/editar", methods=["GET", "POST"])
@login_required(*STAFF)
def paciente_form(paciente_id=None):
    paciente = None
    if paciente_id:
        paciente = query("SELECT * FROM pacientes WHERE id=%s", (paciente_id,), one=True)
        if not paciente:
            flash("Paciente no encontrado.", "warning")
            return redirect(url_for("pacientes_lista"))
    datos = request.form if request.method == "POST" else (paciente or {})

    if request.method == "POST":
        f = request.form
        nombre, correo = f.get("nombre", "").strip(), f.get("correo", "").strip().lower()
        documento, telefono = f.get("documento", "").strip(), f.get("telefono", "").strip()
        fecha_nac, direccion = f.get("fecha_nacimiento", "").strip(), f.get("direccion", "").strip()
        errores = validar_persona(nombre, correo, telefono, documento, fecha_nac)
        if errores:
            flash_errores(errores)
        else:
            valores = (documento, nombre, correo, telefono or None,
                       fecha_nac or None, direccion or None)
            try:
                if paciente:
                    execute("""UPDATE pacientes SET documento=%s, nombre=%s, correo=%s,
                               telefono=%s, fecha_nacimiento=%s, direccion=%s WHERE id=%s""",
                            valores + (paciente_id,))
                    flash("Paciente actualizado correctamente.", "success")
                else:
                    execute("""INSERT INTO pacientes (documento, nombre, correo, telefono,
                               fecha_nacimiento, direccion) VALUES (%s,%s,%s,%s,%s,%s)""", valores)
                    flash("Paciente creado correctamente.", "success")
                return redirect(url_for("pacientes_lista"))
            except mysql.connector.IntegrityError as err:
                flash(dup_message(err), "danger")
    return render_template("paciente_form.html", datos=datos, paciente=paciente)


@app.route("/pacientes/<int:paciente_id>/eliminar", methods=["POST"])
@login_required(*STAFF)
def paciente_eliminar(paciente_id):
    execute("DELETE FROM pacientes WHERE id=%s", (paciente_id,))  # CASCADE borra sus citas
    flash("Paciente eliminado junto con sus citas.", "success")
    return redirect(url_for("pacientes_lista"))


@app.route("/pacientes/<int:paciente_id>/historial")
@login_required()
def historial(paciente_id):
    if session["rol"] == "paciente" and paciente_id != session.get("paciente_id"):
        return render_template("error.html", codigo=403,
                               mensaje="Solo puedes ver tu propio historial."), 403
    paciente = query("SELECT * FROM pacientes WHERE id=%s", (paciente_id,), one=True)
    if not paciente:
        flash("Paciente no encontrado.", "warning")
        return redirect(url_for("dashboard"))
    registros = query("""SELECT h.*, c.fecha, c.hora, c.motivo, mu.nombre AS medico,
                                e.nombre AS especialidad
                         FROM historial_atencion h
                         JOIN citas c ON c.id = h.cita_id
                         JOIN medicos m ON m.id = c.medico_id
                         JOIN usuarios mu ON mu.id = m.usuario_id
                         LEFT JOIN especialidades e ON e.id = m.especialidad_id
                         WHERE c.paciente_id = %s
                         ORDER BY c.fecha DESC, c.hora DESC""", (paciente_id,))
    return render_template("historial.html", paciente=paciente, registros=registros)


@app.route("/mi-historial")
@login_required("paciente")
def mi_historial():
    return redirect(url_for("historial", paciente_id=session.get("paciente_id") or 0))


# ---------------------------------------------------------------------
# 6) CRUD de médicos y especialidades (administrador)
# ---------------------------------------------------------------------
@app.route("/medicos")
@login_required(*STAFF)
def medicos_lista():
    """Obtiene los médicos y añade a cada uno su horario semanal y sus próximas fechas libres. Si se elimina esa preparación, el listado no tendrá los datos para mostrar disponibilidad."""
    medicos = query("""SELECT m.id, u.nombre, u.correo, u.activo, m.telefono,
                              m.registro_profesional, e.nombre AS especialidad
                       FROM medicos m JOIN usuarios u ON u.id = m.usuario_id
                       LEFT JOIN especialidades e ON e.id = m.especialidad_id
                       ORDER BY u.nombre""")
    for medico in medicos:
        medico["horario"] = horario_semanal(medico["id"])
        medico["fechas_disponibles"] = fechas_disponibles(medico["id"], 14)
    return render_template("medicos_lista.html", medicos=medicos, dias=DIAS)


@app.route("/medicos/nuevo", methods=["GET", "POST"])
@app.route("/medicos/<int:medico_id>/editar", methods=["GET", "POST"])
@login_required("administrador")
def medico_form(medico_id=None):
    """Crea o actualiza el perfil del médico y guarda sus jornadas de lunes a domingo. Si se cambia el borrado y guardado de horarios, pueden quedar jornadas antiguas o no guardarse los nuevos días."""
    medico = None
    if medico_id:
        medico = query("""SELECT m.*, u.nombre, u.correo FROM medicos m
                          JOIN usuarios u ON u.id = m.usuario_id WHERE m.id=%s""",
                       (medico_id,), one=True)
        if not medico:
            flash("Médico no encontrado.", "warning")
            return redirect(url_for("medicos_lista"))
    datos = request.form if request.method == "POST" else (medico or {})
    especialidades = query("SELECT * FROM especialidades ORDER BY nombre")

    if request.method == "POST":
        f = request.form
        nombre, correo = f.get("nombre", "").strip(), f.get("correo", "").strip().lower()
        telefono, registro = f.get("telefono", "").strip(), f.get("registro_profesional", "").strip()
        password, esp_id = f.get("password", ""), to_int(f.get("especialidad_id"))
        errores = validar_persona(nombre, correo, telefono)
        if not medico and len(password) < 6:
            errores.append("La contraseña debe tener al menos 6 caracteres.")
        if medico and password and len(password) < 6:
            errores.append("La nueva contraseña debe tener al menos 6 caracteres.")
        for dia, nombre_dia in DIAS:
            if f.get(f"dia_{dia}"):
                inicio_txt, fin_txt = f.get(f"inicio_{dia}", ""), f.get(f"fin_{dia}", "")
                if not inicio_txt or not fin_txt or inicio_txt >= fin_txt:
                    errores.append(f"Revisa el horario del {nombre_dia}: la salida debe ser posterior a la entrada.")
        if errores:
            flash_errores(errores)
        else:
            try:
                with db() as cur:
                    if medico:
                        cur.execute("UPDATE usuarios SET nombre=%s, correo=%s WHERE id=%s",
                                    (nombre, correo, medico["usuario_id"]))
                        if password:
                            cur.execute("UPDATE usuarios SET password_hash=%s WHERE id=%s",
                                        (generate_password_hash(password, method="pbkdf2:sha256"),
                                         medico["usuario_id"]))
                        cur.execute("""UPDATE medicos SET especialidad_id=%s, telefono=%s,
                                       registro_profesional=%s WHERE id=%s""",
                                    (esp_id, telefono or None, registro or None, medico_id))
                        id_medico_guardado = medico_id
                    else:
                        cur.execute("""INSERT INTO usuarios (nombre, correo, password_hash, rol_id)
                                       VALUES (%s,%s,%s,(SELECT id FROM roles WHERE nombre='medico'))""",
                                    (nombre, correo,
                                     generate_password_hash(password, method="pbkdf2:sha256")))
                        cur.execute("""INSERT INTO medicos (usuario_id, especialidad_id, telefono,
                                       registro_profesional) VALUES (%s,%s,%s,%s)""",
                                    (cur.lastrowid, esp_id, telefono or None, registro or None))
                        id_medico_guardado = cur.lastrowid
                    cur.execute("DELETE FROM horarios_medicos WHERE medico_id=%s", (id_medico_guardado,))
                    for dia, _nombre_dia in DIAS:
                        inicio_txt, fin_txt = f.get(f"inicio_{dia}"), f.get(f"fin_{dia}")
                        if f.get(f"dia_{dia}") and inicio_txt and fin_txt:
                            cur.execute("INSERT INTO horarios_medicos (medico_id,dia_semana,hora_inicio,hora_fin,activo) VALUES (%s,%s,%s,%s,1)",
                                        (id_medico_guardado, dia, inicio_txt, fin_txt))
                flash("Médico y horarios guardados correctamente.", "success")
                return redirect(url_for("medicos_lista"))
            except mysql.connector.IntegrityError as err:
                flash(dup_message(err) if err.errno == 1062 else "No se pudo guardar.", "danger")
    horarios_guardados = {h["dia_semana"]: h for h in query("SELECT * FROM horarios_medicos WHERE medico_id=%s", (medico_id,))} if medico_id else {}
    return render_template("medico_form.html", datos=datos, medico=medico,
                           especialidades=especialidades, dias=DIAS, horarios_guardados=horarios_guardados)


@app.route("/medicos/<int:medico_id>/eliminar", methods=["POST"])
@login_required("administrador")
def medico_eliminar(medico_id):
    m = query("SELECT usuario_id FROM medicos WHERE id=%s", (medico_id,), one=True)
    if m:
        try:
            execute("DELETE FROM usuarios WHERE id=%s", (m["usuario_id"],))
            flash("Médico eliminado.", "success")
        except mysql.connector.IntegrityError:
            flash("No se puede eliminar: el médico tiene citas registradas. "
                  "Puedes desactivar su usuario en el módulo Usuarios.", "danger")
    return redirect(url_for("medicos_lista"))


@app.route("/especialidades", methods=["GET", "POST"])
@login_required("administrador")
def especialidades():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if len(nombre) < 3:
            flash("El nombre de la especialidad debe tener al menos 3 caracteres.", "danger")
        else:
            try:
                execute("INSERT INTO especialidades (nombre) VALUES (%s)", (nombre,))
                flash("Especialidad creada.", "success")
            except mysql.connector.IntegrityError:
                flash("Ya existe una especialidad con ese nombre.", "danger")
        return redirect(url_for("especialidades"))
    lista = query("""SELECT e.id, e.nombre, COUNT(m.id) AS medicos FROM especialidades e
                     LEFT JOIN medicos m ON m.especialidad_id = e.id
                     GROUP BY e.id, e.nombre ORDER BY e.nombre""")
    return render_template("especialidades.html", especialidades=lista)


@app.route("/especialidades/<int:esp_id>/editar", methods=["POST"])
@login_required("administrador")
def especialidad_editar(esp_id):
    nombre = request.form.get("nombre", "").strip()
    if len(nombre) < 3:
        flash("El nombre de la especialidad debe tener al menos 3 caracteres.", "danger")
    else:
        try:
            execute("UPDATE especialidades SET nombre=%s WHERE id=%s", (nombre, esp_id))
            flash("Especialidad actualizada.", "success")
        except mysql.connector.IntegrityError:
            flash("Ya existe una especialidad con ese nombre.", "danger")
    return redirect(url_for("especialidades"))


@app.route("/especialidades/<int:esp_id>/eliminar", methods=["POST"])
@login_required("administrador")
def especialidad_eliminar(esp_id):
    execute("DELETE FROM especialidades WHERE id=%s", (esp_id,))  # médicos quedan sin especialidad
    flash("Especialidad eliminada.", "success")
    return redirect(url_for("especialidades"))


# ---------------------------------------------------------------------
# 7) Usuarios del sistema (administrador)
# ---------------------------------------------------------------------
@app.route("/usuarios")
@login_required("administrador")
def usuarios_lista():
    usuarios = query("""SELECT u.id, u.nombre, u.correo, u.activo, r.nombre AS rol
                        FROM usuarios u JOIN roles r ON r.id = u.rol_id
                        ORDER BY r.id, u.nombre""")
    return render_template("usuarios_lista.html", usuarios=usuarios)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required("administrador")
def usuario_nuevo():
    if request.method == "POST":
        f = request.form
        nombre, correo = f.get("nombre", "").strip(), f.get("correo", "").strip().lower()
        rol, password = f.get("rol", ""), f.get("password", "")
        errores = validar_persona(nombre, correo)
        if rol not in STAFF:
            errores.append("Selecciona un rol válido (los médicos se crean en el módulo Médicos).")
        if len(password) < 6:
            errores.append("La contraseña debe tener al menos 6 caracteres.")
        if errores:
            flash_errores(errores)
            return render_template("usuario_form.html", datos=f)
        try:
            execute("""INSERT INTO usuarios (nombre, correo, password_hash, rol_id)
                       VALUES (%s,%s,%s,(SELECT id FROM roles WHERE nombre=%s))""",
                    (nombre, correo, generate_password_hash(password, method="pbkdf2:sha256"), rol))
            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("usuarios_lista"))
        except mysql.connector.IntegrityError as err:
            flash(dup_message(err), "danger")
            return render_template("usuario_form.html", datos=f)
    return render_template("usuario_form.html", datos={})


@app.route("/usuarios/<int:usuario_id>/activar", methods=["POST"])
@login_required("administrador")
def usuario_activar(usuario_id):
    if usuario_id == session["user_id"]:
        flash("No puedes desactivar tu propio usuario.", "warning")
    else:
        execute("UPDATE usuarios SET activo = 1 - activo WHERE id=%s", (usuario_id,))
        flash("Estado del usuario actualizado.", "success")
    return redirect(url_for("usuarios_lista"))


@app.route("/usuarios/<int:usuario_id>/eliminar", methods=["POST"])
@login_required("administrador")
def usuario_eliminar(usuario_id):
    if usuario_id == session["user_id"]:
        flash("No puedes eliminar tu propio usuario.", "warning")
    else:  # solo administradores/recepcionistas; médicos y pacientes se gestionan en su módulo
        execute("""DELETE FROM usuarios WHERE id=%s AND rol_id IN
                   (SELECT id FROM roles WHERE nombre IN ('administrador','recepcionista'))""",
                (usuario_id,))
        flash("Usuario eliminado.", "success")
    return redirect(url_for("usuarios_lista"))


# ---------------------------------------------------------------------
# 8) Citas
# ---------------------------------------------------------------------
SQL_CITAS = """SELECT c.id, c.fecha, c.hora, c.motivo, c.estado, c.paciente_id,
                      p.nombre AS paciente, mu.nombre AS medico,
                      e.nombre AS especialidad, h.id AS historial_id
               FROM citas c
               JOIN pacientes p ON p.id = c.paciente_id
               JOIN medicos m ON m.id = c.medico_id
               JOIN usuarios mu ON mu.id = m.usuario_id
               LEFT JOIN especialidades e ON e.id = m.especialidad_id
               LEFT JOIN historial_atencion h ON h.cita_id = c.id"""


@app.route("/citas")
@login_required()
def citas_lista():
    fecha, estado = request.args.get("fecha", ""), request.args.get("estado", "")
    where, params = [], []
    if session["rol"] == "paciente":
        where.append("c.paciente_id = %s"); params.append(session.get("paciente_id"))
    elif session["rol"] == "medico":
        where.append("c.medico_id = %s"); params.append(session.get("medico_id"))
    if fecha:
        where.append("c.fecha = %s"); params.append(fecha)
    if estado in ESTADOS:
        where.append("c.estado = %s"); params.append(estado)
    sql = SQL_CITAS + (" WHERE " + " AND ".join(where) if where else "")
    citas = query(sql + " ORDER BY c.fecha DESC, c.hora DESC", tuple(params))
    return render_template("citas_lista.html", citas=citas, fecha=fecha,
                           estado=estado, estados=ESTADOS)


@app.route("/api/fechas-disponibles")
@login_required("administrador", "recepcionista", "paciente")
def api_fechas_disponibles():
    """Entrega en formato JSON las fechas futuras que tienen turnos libres para el médico seleccionado. La pantalla de agendamiento consulta esta ruta automáticamente. Si se elimina, no aparecerá la lista de fechas."""
    medico_id = to_int(request.args.get("medico_id"))
    if not medico_id:
        return jsonify({"fechas": [], "mensaje": "Selecciona un médico."})
    existe = query("SELECT id FROM medicos WHERE id=%s", (medico_id,), one=True)
    if not existe:
        return jsonify({"fechas": [], "mensaje": "Médico no encontrado."}), 404
    fechas = fechas_disponibles(medico_id, 30)
    return jsonify({"fechas": fechas,
                    "mensaje": "" if fechas else "No hay fechas con turnos disponibles en los próximos 30 días."})


@app.route("/mi-horario")
@login_required("medico")
def mi_horario():
    """Muestra al médico su jornada semanal y las fechas con turnos libres. Si se elimina, el acceso Mi horario dejará de funcionar."""
    medico_id = session.get("medico_id")
    horario = horario_semanal(medico_id)
    fechas = fechas_disponibles(medico_id, 30)
    return render_template("mi_horario.html", horario=horario, fechas=fechas, dias=DIAS)


@app.route("/api/disponibilidad")
@login_required("administrador", "recepcionista", "paciente")
def api_disponibilidad():
    """Entrega los horarios libres de un médico para una fecha específica. Si se elimina, el selector de horas no podrá actualizarse al cambiar médico o fecha."""
    medico_id = to_int(request.args.get("medico_id"))
    fecha_txt = request.args.get("fecha", "")
    if not medico_id or not fecha_txt:
        return jsonify({"horas": [], "mensaje": "Selecciona un médico y una fecha."})
    try:
        fecha_obj = date.fromisoformat(fecha_txt)
        if fecha_obj < date.today():
            return jsonify({"horas": [], "mensaje": "No puedes seleccionar fechas anteriores."})
    except ValueError:
        return jsonify({"horas": [], "mensaje": "Fecha inválida."}), 400
    excluir_cita = to_int(request.args.get("excluir_cita")) or None
    horas = horas_disponibles(medico_id, fecha_txt, excluir_cita)
    return jsonify({"horas": horas, "mensaje": "" if horas else "El médico no trabaja ese día o no tiene horarios disponibles."})


@app.route("/citas/nueva", methods=["GET", "POST"])
@app.route("/citas/<int:cita_id>/editar", methods=["GET", "POST"])
@login_required("administrador", "recepcionista", "paciente")
def cita_form(cita_id=None):
    """Valida y guarda una cita o reprogramación. Antes de guardar comprueba que el médico trabaje ese día, que el turno siga libre y que el paciente no tenga otra cita a esa hora. Si se quitan esas validaciones, se podrían duplicar citas o reservar fuera de jornada."""
    cita = None
    if cita_id:
        if session["rol"] == "paciente":
            return render_template("error.html", codigo=403,
                                   mensaje="Solo recepción puede reprogramar citas. "
                                           "Puedes cancelarla y crear una nueva."), 403
        cita = query("SELECT * FROM citas WHERE id=%s", (cita_id,), one=True)
        if not cita or cita["estado"] not in ("Programada", "Confirmada"):
            flash("La cita no existe o ya no se puede modificar.", "warning")
            return redirect(url_for("citas_lista"))

    if request.method == "POST":
        datos = request.form
    elif cita:
        datos = dict(cita, hora=filtro_hora(cita["hora"]), fecha=cita["fecha"].isoformat())
    else:
        datos = {}

    pacientes = query("SELECT id, nombre, documento FROM pacientes ORDER BY nombre")
    medicos = query("""SELECT m.id, u.nombre, e.nombre AS especialidad FROM medicos m
                       JOIN usuarios u ON u.id = m.usuario_id AND u.activo = 1
                       LEFT JOIN especialidades e ON e.id = m.especialidad_id
                       ORDER BY u.nombre""")

    if request.method == "POST":
        f = request.form
        paciente_id = session.get("paciente_id") if session["rol"] == "paciente" \
            else to_int(f.get("paciente_id"))
        medico_id = to_int(f.get("medico_id"))
        fecha_txt, hora = f.get("fecha", ""), f.get("hora", "")
        motivo = f.get("motivo", "").strip()
        errores = []
        if not paciente_id:
            errores.append("Selecciona un paciente.")
        if not medico_id:
            errores.append("Selecciona un médico.")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hora):
            errores.append("Selecciona una hora válida.")
        if len(motivo) < 5 or len(motivo) > 255:
            errores.append("El motivo debe tener entre 5 y 255 caracteres.")
        try:
            fecha_cita = date.fromisoformat(fecha_txt)
            if fecha_cita < date.today():
                errores.append("La fecha no puede ser anterior a hoy.")
            elif (fecha_cita == date.today() and hora in HORAS
                  and hora <= datetime.now().strftime("%H:%M")):
                errores.append("Esa hora ya pasó. Elige una hora posterior.")
        except ValueError:
            errores.append("Selecciona una fecha válida.")

        if not errores:  # evitar choques de agenda (médico y paciente)
            actual = cita_id or 0
            choque_medico = query("""SELECT id FROM citas WHERE medico_id=%s AND fecha=%s
                                     AND hora=%s AND estado<>'Cancelada' AND id<>%s""",
                                  (medico_id, fecha_txt, hora, actual), one=True)
            choque_paciente = query("""SELECT id FROM citas WHERE paciente_id=%s AND fecha=%s
                                       AND hora=%s AND estado<>'Cancelada' AND id<>%s""",
                                    (paciente_id, fecha_txt, hora, actual), one=True)
            if choque_medico:
                errores.append("El médico ya tiene una cita en ese horario.")
            disponibles = horas_disponibles(medico_id, fecha_txt, actual)
            if hora not in disponibles:
                errores.append("Ese médico no trabaja ese día o el horario ya no está disponible. Elige una fecha y hora disponibles.")
            if choque_paciente:
                errores.append("El paciente ya tiene una cita en ese horario.")

        if errores:
            flash_errores(errores)
        else:
            try:
                if cita:
                    execute("""UPDATE citas SET paciente_id=%s, medico_id=%s, fecha=%s, hora=%s,
                               motivo=%s WHERE id=%s""",
                            (paciente_id, medico_id, fecha_txt, hora, motivo, cita_id))
                    flash("Cita reprogramada correctamente.", "success")
                else:
                    execute("""INSERT INTO citas (paciente_id, medico_id, fecha, hora, motivo)
                               VALUES (%s,%s,%s,%s,%s)""",
                            (paciente_id, medico_id, fecha_txt, hora, motivo))
                    flash("Cita agendada correctamente.", "success")
                return redirect(url_for("citas_lista"))
            except mysql.connector.IntegrityError:
                flash("No se pudo guardar: paciente o médico inexistente.", "danger")

    horas_iniciales = horas_disponibles(to_int(datos.get("medico_id")), str(datos.get("fecha", "")), cita_id) if datos.get("medico_id") and datos.get("fecha") else []
    return render_template("cita_form.html", datos=datos, cita=cita, pacientes=pacientes,
                           medicos=medicos, horas=horas_iniciales, hoy=date.today().isoformat())


@app.route("/citas/<int:cita_id>/estado", methods=["POST"])
@login_required()
def cita_estado(cita_id):
    nuevo = request.form.get("estado", "")
    cita = query("SELECT * FROM citas WHERE id=%s", (cita_id,), one=True)
    if not cita:
        flash("Cita no encontrada.", "warning")
        return redirect(url_for("citas_lista"))
    rol, ok = session["rol"], False
    if nuevo == "Confirmada" and rol in STAFF and cita["estado"] == "Programada":
        ok = True
    elif nuevo == "Cancelada" and cita["estado"] in ("Programada", "Confirmada"):
        ok = (rol in STAFF
              or (rol == "paciente" and cita["paciente_id"] == session.get("paciente_id"))
              or (rol == "medico" and cita["medico_id"] == session.get("medico_id")))
    if ok:
        execute("UPDATE citas SET estado=%s WHERE id=%s", (nuevo, cita_id))
        flash(f"Cita {nuevo.lower()}.", "success")
    else:
        flash("No tienes permiso o el cambio de estado no es válido.", "danger")
    return redirect(url_for("citas_lista"))


@app.route("/citas/<int:cita_id>/eliminar", methods=["POST"])
@login_required("administrador")
def cita_eliminar(cita_id):
    execute("DELETE FROM citas WHERE id=%s", (cita_id,))
    flash("Cita eliminada.", "success")
    return redirect(url_for("citas_lista"))


@app.route("/citas/<int:cita_id>/atender", methods=["GET", "POST"])
@login_required("medico")
def atender(cita_id):
    """Registra el diagnóstico, tratamiento y observaciones de una consulta y cambia la cita a estado Atendida. Si se elimina, el médico no podrá registrar la atención."""
    cita = query(SQL_CITAS + " WHERE c.id=%s", (cita_id,), one=True)
    propia = query("SELECT medico_id FROM citas WHERE id=%s", (cita_id,), one=True)
    if not cita or propia["medico_id"] != session.get("medico_id"):
        flash("Cita no encontrada.", "warning")
        return redirect(url_for("citas_lista"))
    if cita["estado"] == "Cancelada":
        flash("No se puede atender una cita cancelada.", "warning")
        return redirect(url_for("citas_lista"))
    hist = query("SELECT * FROM historial_atencion WHERE cita_id=%s", (cita_id,), one=True)
    datos = request.form if request.method == "POST" else (hist or {})

    if request.method == "POST":
        diag = request.form.get("diagnostico", "").strip()
        trat = request.form.get("tratamiento", "").strip()
        obs = request.form.get("observaciones", "").strip()
        if len(diag) < 5:
            flash("El diagnóstico debe tener al menos 5 caracteres.", "danger")
        else:
            with db() as cur:
                if hist:
                    cur.execute("""UPDATE historial_atencion SET diagnostico=%s, tratamiento=%s,
                                   observaciones=%s WHERE cita_id=%s""",
                                (diag, trat or None, obs or None, cita_id))
                else:
                    cur.execute("""INSERT INTO historial_atencion (cita_id, diagnostico,
                                   tratamiento, observaciones) VALUES (%s,%s,%s,%s)""",
                                (cita_id, diag, trat or None, obs or None))
                cur.execute("UPDATE citas SET estado='Atendida' WHERE id=%s", (cita_id,))
            flash("Atención registrada en el historial.", "success")
            return redirect(url_for("citas_lista"))
    return render_template("atender.html", cita=cita, datos=datos)


# ---------------------------------------------------------------------
# 9) Reporte de citas (con filtros y exportación a CSV)
# ---------------------------------------------------------------------
def datos_reporte():
    """Filtra las citas por fechas, médico y estado. Se utiliza tanto en la pantalla de reportes como en la exportación CSV. Si se quita, los reportes perderán sus filtros y datos."""
    hoy = date.today()
    desde = request.args.get("desde") or (hoy - timedelta(days=30)).isoformat()
    hasta = request.args.get("hasta") or (hoy + timedelta(days=30)).isoformat()
    medico_id, estado = to_int(request.args.get("medico_id")), request.args.get("estado", "")
    where, params = ["c.fecha BETWEEN %s AND %s"], [desde, hasta]
    if medico_id:
        where.append("c.medico_id = %s"); params.append(medico_id)
    if estado in ESTADOS:
        where.append("c.estado = %s"); params.append(estado)
    filas = query(SQL_CITAS + " WHERE " + " AND ".join(where) +
                  " ORDER BY c.fecha, c.hora", tuple(params))
    return filas, desde, hasta, medico_id, estado


@app.route("/reportes")
@login_required(*STAFF)
def reportes():
    filas, desde, hasta, medico_id, estado = datos_reporte()
    por_estado = Counter(f["estado"] for f in filas)
    por_medico = {}
    for f in filas:
        d = por_medico.setdefault(f["medico"], Counter())
        d["total"] += 1
        d[f["estado"]] += 1
    medicos = query("""SELECT m.id, u.nombre FROM medicos m
                       JOIN usuarios u ON u.id = m.usuario_id ORDER BY u.nombre""")
    return render_template("reportes.html", filas=filas, desde=desde, hasta=hasta,
                           medico_id=medico_id, estado=estado, estados=ESTADOS,
                           medicos=medicos, por_estado=por_estado, por_medico=por_medico)


@app.route("/reportes/csv")
@login_required(*STAFF)
def reportes_csv():
    """Prepara y descarga las citas filtradas como archivo CSV compatible con Excel. Si se elimina, los reportes seguirán en pantalla, pero no se podrán descargar."""
    filas = datos_reporte()[0]
    salida = io.StringIO()
    salida.write("\ufeff")  # BOM para que Excel respete las tildes
    w = csv.writer(salida, delimiter=";")
    w.writerow(["Fecha", "Hora", "Paciente", "Médico", "Especialidad", "Motivo", "Estado"])
    for f in filas:
        w.writerow([f["fecha"], filtro_hora(f["hora"]), f["paciente"], f["medico"],
                    f["especialidad"] or "", f["motivo"], f["estado"]])
    return Response(salida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=reporte_citas.csv"})


# ---------------------------------------------------------------------
# 10) Punto de entrada de desarrollo
# ---------------------------------------------------------------------
# Para probar el proyecto en el computador se ejecuta este archivo directamente.
# debug=True muestra errores detallados y recarga al guardar cambios; úsalo solo en desarrollo.
# En un despliegue público debe usarse un servidor de producción y una SECRET_KEY segura.
if __name__ == "__main__":
    app.run(debug=True)
