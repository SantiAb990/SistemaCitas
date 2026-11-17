-- Base de datos del Sistema de Gestión de Citas Médicas
CREATE DATABASE IF NOT EXISTS sistema_citas
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_general_ci;

USE sistema_citas;

-- 1) Roles del sistema (administrador, recepcionista, medico, paciente)
CREATE TABLE IF NOT EXISTS roles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(30) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- 2) Usuarios que inician sesión (1:N con roles)
CREATE TABLE IF NOT EXISTS usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  correo VARCHAR(100) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  rol_id INT NOT NULL,
  activo TINYINT(1) NOT NULL DEFAULT 1,
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rol_id) REFERENCES roles(id)
) ENGINE=InnoDB;

-- 3) Especialidades médicas (1:N con médicos)
CREATE TABLE IF NOT EXISTS especialidades (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- 4) Médicos: perfil profesional ligado a un usuario (1:1) y a una especialidad
CREATE TABLE IF NOT EXISTS medicos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL UNIQUE,
  especialidad_id INT NULL,
  telefono VARCHAR(20),
  registro_profesional VARCHAR(30) UNIQUE,
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  FOREIGN KEY (especialidad_id) REFERENCES especialidades(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 4.1) Jornada laboral semanal de cada médico (0=lunes ... 6=domingo)
CREATE TABLE IF NOT EXISTS horarios_medicos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  medico_id INT NOT NULL,
  dia_semana TINYINT NOT NULL,
  hora_inicio TIME NOT NULL,
  hora_fin TIME NOT NULL,
  activo TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_medico_dia (medico_id, dia_semana),
  CONSTRAINT fk_horario_medico FOREIGN KEY (medico_id) REFERENCES medicos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 5) Pacientes (pueden o no tener usuario para iniciar sesión)
CREATE TABLE IF NOT EXISTS pacientes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NULL UNIQUE,
  documento VARCHAR(20) NOT NULL UNIQUE,
  nombre VARCHAR(100) NOT NULL,
  correo VARCHAR(100),
  telefono VARCHAR(20),
  fecha_nacimiento DATE NULL,
  direccion VARCHAR(150),
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 6) Citas: une paciente y médico en una fecha y hora (N:M con datos propios)
CREATE TABLE IF NOT EXISTS citas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  paciente_id INT NOT NULL,
  medico_id INT NOT NULL,
  fecha DATE NOT NULL,
  hora TIME NOT NULL,
  motivo VARCHAR(255) NOT NULL,
  estado ENUM('Programada','Confirmada','Atendida','Cancelada') NOT NULL DEFAULT 'Programada',
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  -- Si se borra un paciente se borran sus citas; un médico con citas no se puede borrar
  FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
  FOREIGN KEY (medico_id) REFERENCES medicos(id) ON DELETE RESTRICT,
  INDEX idx_agenda (medico_id, fecha, hora)
) ENGINE=InnoDB;

-- 7) Historial de atención: diagnóstico registrado por el médico (1:1 con cita)
CREATE TABLE IF NOT EXISTS historial_atencion (
  id INT AUTO_INCREMENT PRIMARY KEY,
  cita_id INT NOT NULL UNIQUE,
  diagnostico TEXT NOT NULL,
  tratamiento TEXT,
  observaciones TEXT,
  registrado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (cita_id) REFERENCES citas(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- DATOS DE PRUEBA
-- Contraseñas: Admin123 / Recep123 / Medico123 / Paciente123
-- ---------------------------------------------------------------
INSERT IGNORE INTO roles (id, nombre) VALUES
(1,'administrador'),(2,'recepcionista'),(3,'medico'),(4,'paciente');

INSERT IGNORE INTO especialidades (id, nombre) VALUES
(1,'Medicina General'),(2,'Pediatría'),(3,'Cardiología'),
(4,'Dermatología'),(5,'Odontología'),(6,'Ginecología');

INSERT IGNORE INTO usuarios (id, nombre, correo, password_hash, rol_id) VALUES
(1,'Admin Sistema','admin@citas.com','pbkdf2:sha256:1000000$AU54NVjN7uuVcIcG$4bcde66f18d54bdde3ec2ab4942b655ee347c7d4442381456915fc4b8c70d22e',1),
(2,'Laura Recepción','recepcion@citas.com','pbkdf2:sha256:1000000$IfkU4bFePwFFjDdp$1d98e76cab512404c7c2be29e3ed3509492be534c9f97673ff73c3244c63248a',2),
(3,'Dr. Carlos Mendoza','medico@citas.com','pbkdf2:sha256:1000000$8gtegm8CQLsh2KFK$5ac19dd2fb2a585f0789afc19680b1f3cbc379892bea172fdd8c547790f87ccf',3),
(4,'Dra. Ana Torres','ana.torres@citas.com','pbkdf2:sha256:1000000$gPBGNPRXYVf3QAIT$cae12f60d376465d6c5d065e2b31a1428b4f5dbd376e5374f6c510dbf1505ef4',3),
(5,'Paciente Demo','paciente@citas.com','pbkdf2:sha256:1000000$0f1wreCuykTmTGo1$eb636a60d4b1ae6aa496499bb90ad985f06b3c2eb659ce56883ce36e6bc302b0',4);

INSERT IGNORE INTO medicos (id, usuario_id, especialidad_id, telefono, registro_profesional) VALUES
(1,3,1,'3001112233','RM-1001'),
(2,4,2,'3004445566','RM-1002');

-- Jornada inicial de ejemplo: lunes a viernes, 08:00 a 17:00.
INSERT IGNORE INTO horarios_medicos (medico_id, dia_semana, hora_inicio, hora_fin)
SELECT m.id, d.dia, '08:00:00', '17:00:00'
FROM medicos m
CROSS JOIN (SELECT 0 AS dia UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4) d;

INSERT IGNORE INTO pacientes (id, usuario_id, documento, nombre, correo, telefono, fecha_nacimiento, direccion) VALUES
(1,5,'1001234567','Paciente Demo','paciente@citas.com','3101234567','1995-04-12','Calle 10 # 5-20'),
(2,NULL,'1009876543','María Gómez','maria@correo.com','3109876543','1988-09-30','Carrera 7 # 12-45'),
(3,NULL,'1005554443','Juan Pérez','juan@correo.com','3105554443','2015-01-20','Av. Principal 100');

INSERT IGNORE INTO citas (id, paciente_id, medico_id, fecha, hora, motivo, estado) VALUES
(1,1,1,CURDATE()+INTERVAL 1 DAY,'09:00:00','Dolor de cabeza frecuente','Programada'),
(2,1,2,CURDATE()+INTERVAL 3 DAY,'10:30:00','Control general','Confirmada'),
(3,1,1,CURDATE()-INTERVAL 10 DAY,'08:30:00','Chequeo anual','Atendida'),
(4,2,1,CURDATE(),'15:00:00','Gripa y fiebre','Confirmada'),
(5,2,2,CURDATE()-INTERVAL 3 DAY,'11:00:00','Control de crecimiento','Atendida'),
(6,3,1,CURDATE()-INTERVAL 1 DAY,'14:00:00','Consulta general','Cancelada'),
(7,3,2,CURDATE()+INTERVAL 2 DAY,'16:00:00','Vacunación','Programada');

INSERT IGNORE INTO historial_atencion (id, cita_id, diagnostico, tratamiento, observaciones) VALUES
(1,3,'Paciente sano, sin hallazgos relevantes.','Mantener hábitos saludables.','Control en 12 meses.'),
(2,5,'Crecimiento acorde a la edad.','Suplemento vitamínico por 30 días.','Volver si hay fiebre o pérdida de apetito.');
