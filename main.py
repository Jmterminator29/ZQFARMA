from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dbfread import DBF
from dbf import Table, READ_WRITE
from datetime import datetime
import threading
import requests
import unicodedata
import os

# ================================
# CONFIGURACIÓN FASTAPI
# ================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================
# ARCHIVOS DBF
# ================================
ZETH50T = "ZETH50T.DBF"
ZETH51T = "ZETH51T.DBF"
ZETH70 = "ZETH70.DBF"
ZETH70_EXT = "ZETH70_EXT.DBF"
HISTORICO_DBF = "VENTAS_HISTORICO.DBF"

CAMPOS_HISTORICO = (
    "EERR C(20);"
    "FECHA D;"
    "N_TICKET C(10);"
    "NOMBRES C(50);"
    "TIPO C(5);"
    "CANT N(6,0);"
    "P_UNIT N(12,2);"
    "CATEGORIA C(20);"
    "SUB_CAT C(20);"
    "COST_UNIT N(12,2);"
    "PRONUM C(10);"
    "DESCRI C(50)"
)

# ================================
# FUNCIONES AUXILIARES
# ================================
def limpiar_ascii(texto):
    """Convierte texto a ASCII seguro para evitar errores en Render"""
    if isinstance(texto, str):
        return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return texto

def crear_dbf_historico():
    if not os.path.exists(HISTORICO_DBF):
        table = Table(HISTORICO_DBF, CAMPOS_HISTORICO, codepage="cp850")
        table.open(mode=READ_WRITE)
        table.close()

def leer_dbf_existente():
    if not os.path.exists(HISTORICO_DBF):
        return set()
    return {r["N_TICKET"] for r in DBF(HISTORICO_DBF, load=True, encoding="cp850")}

def agregar_al_historico(nuevos_registros):
    table = Table(HISTORICO_DBF)
    table.open(mode=READ_WRITE)
    for reg in nuevos_registros:
        table.append(reg)
    table.close()

def obtener_costo_producto(pronum, productos):
    producto = productos.get(pronum)
    if producto:
        return float(producto.get("ULCOSREP", 0.0))
    return 0.0

# ================================
# ENDPOINTS
# ================================
@app.get("/")
def home():
    return {
        "mensaje": "API activa en Render",
        "usar_endpoint": "/historico → Devuelve datos guardados",
        "actualizar": "/reporte → Actualiza el histórico",
        "descargar": "/descargar/historico → Descarga el archivo DBF"
    }

@app.get("/historico")
def historico_json():
    if not os.path.exists(HISTORICO_DBF):
        return {"total": 0, "datos": []}
    datos = list(DBF(HISTORICO_DBF, load=True, encoding="cp850"))
    # Limpiar para evitar errores ASCII en Render
    datos_limpios = [{k: limpiar_ascii(v) for k, v in row.items()} for row in datos]
    return {"total": len(datos_limpios), "datos": datos_limpios}

@app.get("/reporte")
def generar_reporte():
    try:
        for archivo in [ZETH50T, ZETH51T, ZETH70]:
            if not os.path.exists(archivo):
                return {"error": f"No se encontró {archivo}"}

        crear_dbf_historico()
        tickets_existentes = leer_dbf_existente()

        productos = {r["PRONUM"]: r for r in DBF(ZETH70, load=True, encoding="cp850")}
        productos_ext = (
            {r["PRONUM"]: r for r in DBF(ZETH70_EXT, load=True, encoding="cp850")}
            if os.path.exists(ZETH70_EXT)
            else {}
        )
        cabeceras = {r["NUMCHK"]: r for r in DBF(ZETH50T, load=True, encoding="cp850")}

        fecha_inicio = datetime(2025, 3, 1)
        fecha_hoy = datetime.today()

        nuevos_registros = []

        for detalle in DBF(ZETH51T, load=True, encoding="cp850"):
            numchk = detalle["NUMCHK"]
            if numchk in tickets_existentes:
                continue

            cab = cabeceras.get(numchk)
            if not cab:
                continue

            fecchk = cab.get("FECCHK")
            if fecchk:
                if isinstance(fecchk, str):
                    try:
                        fecchk = datetime.strptime(fecchk.strip(), "%Y-%m-%d").date()
                    except:
                        try:
                            fecchk = datetime.strptime(fecchk.strip(), "%d/%m/%Y").date()
                        except:
                            continue
                elif isinstance(fecchk, datetime):
                    fecchk = fecchk.date()

                if not (fecha_inicio.date() <= fecchk <= fecha_hoy.date()):
                    continue

            pronum = detalle.get("PRONUM", "")
            prod_ext = productos_ext.get(pronum, {})
            cost_unit = obtener_costo_producto(pronum, productos)

            cant = float(detalle.get("QTYPRO", 0))
            p_unit = float(detalle.get("PRIPRO", 0))

            nuevo = {
                "EERR": prod_ext.get("EERR", ""),
                "FECHA": fecchk,
                "N_TICKET": cab.get("NUMCHK", ""),
                "NOMBRES": cab.get("CUSNAM", ""),
                "TIPO": cab.get("TYPPAG", ""),
                "CANT": cant,
                "P_UNIT": p_unit,
                "CATEGORIA": prod_ext.get("CATEGORIA", ""),
                "SUB_CAT": prod_ext.get("SUB_CAT", ""),
                "COST_UNIT": cost_unit,
                "PRONUM": pronum,
                "DESCRI": prod_ext.get("DESCRI", "")
            }

            nuevos_registros.append(nuevo)

        if nuevos_registros:
            agregar_al_historico(nuevos_registros)

        # 🔥 Limpiar todo antes de devolver
        registros_limpios = [
            {k: limpiar_ascii(v) for k, v in reg.items()}
            for reg in nuevos_registros
        ]

        return {"total": len(registros_limpios), "nuevos": registros_limpios}

    except Exception as e:
        return {"error": limpiar_ascii(e)}

@app.get("/descargar/historico")
def descargar_historico():
    if not os.path.exists(HISTORICO_DBF):
        return {"error": "El archivo histórico aún no existe."}
    return FileResponse(
        HISTORICO_DBF,
        media_type="application/octet-stream",
        filename=HISTORICO_DBF
    )

# ================================
# EJECUTAR /REPORTE AUTOMÁTICAMENTE AL INICIAR (SIN LOGS)
# ================================
def actualizar_historico_automatico():
    try:
        requests.get("https://zqfarma.onrender.com/reporte", timeout=30)
    except:
        pass

threading.Thread(target=actualizar_historico_automatico).start()







