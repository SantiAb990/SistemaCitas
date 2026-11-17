# Guía para explicar el código de MediCitas

Esta guía está pensada para estudiantes que están comenzando. El proyecto está dividido por responsabilidades para que sea más fácil seguir el recorrido de una acción.

## 1. Estructura de carpetas

- `app.py`: rutas, reglas y comunicación entre la página y la base de datos.
- `templates/`: pantallas HTML que ve el usuario.
- `schema.sql`: estructura inicial de las tablas de MySQL.
- `migracion_horarios_medicos.sql`: crea la tabla de jornadas de los médicos en una base de datos existente.
- `requirements.txt`: librerías de Python necesarias para ejecutar el proyecto.
- `tests/`: pruebas que ayudan a comprobar las funciones principales.

Si se cambia el nombre de una carpeta o archivo, también hay que actualizar las referencias que lo utilizan.

## 2. Recorrido de una cita

1. El paciente abre `cita_form.html` y selecciona un médico.
2. JavaScript consulta `/api/fechas-disponibles` para mostrar fechas que tienen turnos libres.
3. Al elegir una fecha, consulta `/api/disponibilidad` para obtener las horas libres.
4. El formulario envía los datos a la función `cita_form()` de `app.py`.
5. Flask vuelve a comprobar las reglas antes de guardar. Esta segunda comprobación es importante: el navegador no debe ser la única barrera contra reservas duplicadas.
6. La función `execute()` guarda la cita en MySQL.

## 3. Funciones importantes de `app.py`

| Función | ¿Para qué sirve? | ¿Qué pasa si se quita o cambia mal? |
|---|---|---|
| `get_db_connection()` | Conecta Flask con MySQL. | El sistema no puede leer ni guardar datos. |
| `db()` | Abre y cierra conexión y confirma o revierte operaciones. | Pueden quedar cambios sin guardar o conexiones abiertas. |
| `query()` | Ejecuta consultas de lectura (`SELECT`). | Las pantallas no reciben los datos que necesitan. |
| `execute()` | Ejecuta altas, cambios y eliminaciones. | No se podrían guardar cambios en la base de datos. |
| `horas_disponibles()` | Calcula turnos de 30 minutos según jornada y citas ocupadas. | Se podrían ofrecer horas fuera de jornada o ya reservadas. |
| `fechas_disponibles()` | Busca los días futuros que tienen al menos un turno libre. | No se podrían sugerir fechas al paciente. |
| `horario_semanal()` | Consulta la jornada configurada de cada médico. | Los perfiles y paneles no mostrarían sus días de trabajo. |
| `login_required()` | Protege las páginas según el rol. | Se debilitaría el control de acceso. |
| `login()` | Verifica credenciales y crea la sesión. | Los usuarios no podrían entrar correctamente. |
| `dashboard()` | Prepara indicadores y datos del panel. | El inicio quedaría sin estadísticas ni resúmenes. |
| `medicos_lista()` | Carga médicos, jornadas y fechas disponibles. | El listado no podría mostrar la disponibilidad. |
| `medico_form()` | Crea o modifica al médico y su horario semanal. | No se podrían administrar las jornadas desde el formulario. |
| `api_fechas_disponibles()` | Devuelve las fechas libres en formato JSON. | El selector de fechas no se actualizaría. |
| `api_disponibilidad()` | Devuelve las horas libres para un día. | El selector de horas no mostraría los turnos actuales. |
| `mi_horario()` | Muestra el horario del médico que inició sesión. | Desaparecería la pantalla “Mi horario”. |
| `cita_form()` | Valida y guarda o reprograma una cita. | No habría un proceso central para agendar con validaciones. |
| `atender()` | Guarda diagnóstico, tratamiento y observaciones. | El médico no podría registrar la atención. |
| `datos_reporte()` | Aplica filtros para construir los reportes. | Los reportes perderían sus filtros y resultados correctos. |
| `reportes_csv()` | Descarga el reporte en formato CSV para Excel. | No habría botón de exportación. |

## 4. Archivos de pantalla

- `base.html`: estructura común y barra superior. Si se quita, las páginas pierden el menú compartido y los estilos generales.
- `dashboard.html`: indicadores, gráficos y resumen de horarios. Si se quita, no se muestra el panel de inicio.
- `medicos_lista.html`: listado de médicos, jornada y fechas próximas.
- `medico_form.html`: formulario para crear/editar un médico y marcar sus días laborales.
- `mi_horario.html`: vista personal de la jornada del médico.
- `cita_form.html`: formulario de cita y JavaScript que actualiza fechas y horas. Si se quita ese JavaScript, el usuario tendría que recargar manualmente y no vería la disponibilidad dinámica.

## 5. Barra superior

La barra está en `templates/base.html`. Los enlaces se muestran según el rol guardado en la sesión. Las clases CSS `.barra-principal`, `.navbar-nav .nav-link` y `.activo` controlan el color, tamaño, separación y resaltado de la sección actual. Si se cambia el CSS, solo cambia la presentación; si se quitan las condiciones `{% if rol ... %}`, se puede mostrar un enlace a un usuario que no debería tenerlo. La seguridad real también se mantiene en las rutas con `login_required()`.

## 6. Recomendaciones para la exposición

- Explicar primero el recorrido de una cita y luego enseñar las funciones en ese mismo orden.
- Mostrar un ejemplo de médico con días laborales configurados.
- Cambiar la fecha de una cita y observar cómo se actualizan las horas disponibles.
- Explicar que el servidor vuelve a validar la disponibilidad antes de guardar, aunque el navegador ya la haya consultado.
- No borrar funciones solo porque su nombre parezca largo: primero revisar quién las utiliza.

## 7. Nota de configuración

Los datos de conexión de MySQL se encuentran en `DB_CONFIG` dentro de `app.py`. El puerto debe coincidir con el configurado en XAMPP. La clave `SECRET_KEY` debe cambiarse antes de publicar el sistema en Internet. `debug=True` se usa para desarrollo local, no para un servidor público.
