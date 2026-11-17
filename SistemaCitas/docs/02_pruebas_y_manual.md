# Matriz de pruebas funcionales y manual de usuario

## 1. Matriz de pruebas
Las pruebas P01–P48 están automatizadas en `tests/pruebas_funcionales.py`
(resultado de la última ejecución: **51/51 correctas**). Resumen por criterio:

| Criterio | Pruebas | Resultado esperado |
|---|---|---|
| Login y sesión | P01–P04 | Sin sesión redirige al login; credenciales inválidas muestran error; logout cierra sesión |
| Control de acceso por rol | P05–P12 | Cada rol solo entra a sus módulos; los demás responden 403 |
| CRUD pacientes | P13–P17, P48 | Crear, consultar, actualizar y eliminar (con cascada a citas) |
| Validaciones | P14, P15, P20, P21, P29, P47 | Mensajes claros ante datos inválidos o duplicados |
| Citas | P18–P27 | Agendar, reprogramar, confirmar, cancelar; sin choques ni fechas pasadas |
| Historial | P28–P35 | Solo el médico dueño atiende; el paciente ve solo su historial |
| Dashboard | P36 | Indicadores por rol |
| Reporte | P37–P39 | Filtros y exportación CSV |
| Administración | P40–P46 | Crear médicos, especialidades, usuarios; integridad referencial |

### Pruebas manuales sugeridas para la sustentación
| Qué hacer | Qué debes ver |
|---|---|
| Entrar como recepcion@citas.com y agendar una cita | Aparece en el listado como *Programada* |
| Intentar la misma hora con el mismo médico | Mensaje "El médico ya tiene una cita en ese horario" |
| Confirmar la cita | Estado *Confirmada* |
| Entrar como medico@citas.com → Atender | Se guarda el diagnóstico y la cita pasa a *Atendida* |
| Entrar como paciente@citas.com → Mi historial | Aparece el diagnóstico registrado |
| Entrar como admin@citas.com → Dashboard | Tarjetas y dos gráficos con datos |
| Reportes → filtrar → CSV | Se descarga `reporte_citas.csv` |

## 2. Manual de usuario
**Ingreso.** Abra http://127.0.0.1:5000, escriba correo y contraseña. Los pacientes nuevos usan *Regístrate*.

**Paciente.** *Citas → Agendar cita*: elija médico, fecha, hora y motivo. Puede cancelar sus citas abiertas. *Mi historial* muestra sus diagnósticos.

**Recepcionista.** *Pacientes*: crear, editar, eliminar y buscar. *Citas*: agendar para cualquier paciente, confirmar, reprogramar o cancelar. *Reportes*: elija fechas, médico y estado; use CSV para exportar o el botón de impresora.

**Médico.** *Citas* muestra solo su agenda. Botón *Atender* → complete diagnóstico (obligatorio), tratamiento y observaciones. *Pacientes → Historial* permite revisar antecedentes.

**Administrador.** Además de lo anterior: *Médicos* (crear con usuario y especialidad), *Especialidades*, *Usuarios* (crear recepcionistas/administradores, activar o desactivar) y *Dashboard* general.

**Errores frecuentes**
| Síntoma | Solución |
|---|---|
| Can't connect to MySQL server | Iniciar MySQL en XAMPP |
| Unknown database 'sistema_citas' | Importar `schema.sql` en phpMyAdmin |
| Access denied for user 'root' | Definir la variable `DB_PASSWORD` |
| 403 Sin permiso | El rol no tiene acceso a ese módulo (es lo esperado) |

## 3. Guion de sustentación (10 min) y distribución de roles
1. Problema y objetivos (1 min). 2. Modelo de datos y arquitectura (2 min). 3. Demo por roles: paciente → recepción → médico → admin (5 min). 4. Pruebas y cierre (2 min).
Sugerencia de reparto: integrante A – análisis/BD; B – backend y roles; C – frontend/dashboard; D – pruebas y documentación.
