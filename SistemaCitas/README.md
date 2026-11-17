# MediCitas – Sistema de gestión de citas médicas

Flask + MySQL (XAMPP) + Jinja2 + Bootstrap 5.

## Instalación (Windows + XAMPP)
1. Abre **XAMPP Control Panel** y pulsa **Start** en MySQL.
2. Abre phpMyAdmin (http://localhost/phpmyadmin) → pestaña **Importar** → selecciona `schema.sql` → Continuar.
   (Crea la base `sistema_citas`, las 7 tablas y datos de prueba.)
3. En la carpeta del proyecto:
   ```
   pip install -r requirements.txt
   python app.py
   ```
4. Abre http://127.0.0.1:5000

Si tu MySQL tiene contraseña para root, define antes de ejecutar:
`set DB_PASSWORD=tu_clave` (CMD) o `$env:DB_PASSWORD="tu_clave"` (PowerShell).

## Horarios y disponibilidad de médicos
- En **Médicos → Editar/Nuevo médico**, el administrador configura los días y horas de trabajo.
- Cada turno de cita dura 30 minutos.
- Al agendar, el paciente/recepción selecciona médico y fecha; el sistema consulta automáticamente los turnos libres.
- No permite reservar días no laborables, horas fuera de jornada ni turnos ocupados.
- Si ya tienes la base de datos creada, importa `migracion_horarios_medicos.sql` desde phpMyAdmin antes de iniciar la aplicación. Esta migración crea la tabla de horarios y asigna inicialmente lunes a viernes de 08:00 a 17:00 a los médicos existentes. Después puedes personalizar cada jornada desde el sistema.
- Si vas a crear la base desde cero, `schema.sql` ya incluye la tabla y horarios iniciales.

## Usuarios de prueba
| Rol | Correo | Contraseña |
|---|---|---|
| Administrador | admin@citas.com | Admin123 |
| Recepcionista | recepcion@citas.com | Recep123 |
| Médico | medico@citas.com | Medico123 |
| Médico (2) | ana.torres@citas.com | Medico123 |
| Paciente | paciente@citas.com | Paciente123 |

## Estructura
```
SistemaCitas/
|- app.py                 rutas, lógica de negocio, validaciones, login y roles
|- schema.sql             7 tablas relacionadas + datos de prueba
|- requirements.txt
|- templates/             base, login, registro, dashboard, CRUD, reportes
|- tests/pruebas_funcionales.py   51 pruebas automáticas
`- docs/                  análisis, diseño, pruebas y manual de usuario
```

## Pruebas automáticas
Con MySQL encendido y `schema.sql` cargado: `python tests/pruebas_funcionales.py`
(modifica datos de prueba; para dejar la base limpia, vuelve a importar `schema.sql`
después de borrar la base `sistema_citas`).

## Permisos por rol
| Módulo | Admin | Recepción | Médico | Paciente |
|---|---|---|---|---|
| Dashboard | ✔ | ✔ | ✔ (sus datos) | ✔ (sus datos) |
| Pacientes (CRUD) | ✔ | ✔ | solo consulta | — |
| Médicos / Especialidades | ✔ | consulta médicos | — | — |
| Usuarios | ✔ | — | — | — |
| Citas | todas, CRUD | agendar, confirmar, reprogramar, cancelar | ve las suyas, atiende | agenda y cancela las suyas |
| Historial | ✔ | ✔ | ✔ | solo el suyo |
| Reportes + CSV | ✔ | ✔ | — | — |

## Vista completa de horarios y disponibilidad
- El panel de administración muestra una tarjeta por médico con su jornada semanal y las fechas con turnos libres de los próximos 14 días.
- En **Médicos**, el administrador y recepción pueden consultar el horario de cada profesional y un resumen de fechas disponibles.
- El médico dispone de **Mi horario** en el menú, con su jornada de lunes a domingo y fechas/horas libres para los próximos 30 días.
- Al agendar una cita, el sistema muestra las próximas fechas disponibles del médico seleccionado. Al elegir una fecha, carga sus horas libres.
- La disponibilidad se calcula en tiempo real según la jornada activa y las citas no canceladas. Los turnos son de 30 minutos.
