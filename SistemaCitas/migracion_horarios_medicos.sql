USE sistema_citas;

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

INSERT IGNORE INTO horarios_medicos (medico_id, dia_semana, hora_inicio, hora_fin)
SELECT m.id, d.dia, '08:00:00', '17:00:00'
FROM medicos m
CROSS JOIN (SELECT 0 AS dia UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4) d;
