
import os
import mysql.connector
from dotenv import load_dotenv
from pathlib import Path

# Buscar el archivo .env dentro de SistemaCitas
BASE_DIR = Path(__file__).resolve().parent / "SistemaCitas"
load_dotenv(BASE_DIR / ".env")

try:
    conexion = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "4000")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl_ca=str(BASE_DIR / "certs" / "ca.pem"),
        ssl_verify_cert=True,
        connection_timeout=15
    )

    print("¡CONEXIÓN EXITOSA CON TiDB CLOUD!")

    cursor = conexion.cursor()
    cursor.execute("SHOW TABLES")

    print("\nTablas encontradas:")
    for tabla in cursor.fetchall():
        print(tabla[0])

    cursor.close()
    conexion.close()

except Exception as error:
    print("ERROR DE CONEXIÓN:")
    print(error)
