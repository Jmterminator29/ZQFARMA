from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dbf import Table, READ_WRITE
from dbfread import DBF
from datetime import datetime, date
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
# ENDPOINTS
# ================================

@app.get("/")
def root():
    return {"status": "OK", "msg": "API DBF Histórico corriendo correctamente"}

@app.get("/historico")
def get_historico():
    """ Devuelve el contenido del histórico en JSON """
    if not os.path.exists("VENTAS_HISTORICO.DBF"):
        return {"status": "error", "msg": "No existe el histórico aún"}
    
    data = []
    for row in DBF("VENTAS_HISTORICO.DBF", load=True, encoding="latin-1"):
        data.append(dict(row))
    return {"status": "ok", "data": data}

@app.get("/descargar/historico")
def descargar_historico():
    """ Permite descargar el histórico completo como archivo DBF """
    if not os.path.exists("VENTAS_HISTORICO.DBF"):
        return {"status": "error", "msg": "No existe el histórico aún"}
    return FileResponse("VENTAS_HISTORICO.DBF", media_type="application/octet-stream", filename="VENTAS_HISTORICO.DBF")

@app.get("/reporte")
def generar_historico():
    """
    Actualiza el VENTAS_HISTORICO.DBF agregando solo registros nuevos del día.
    Si el histórico no existe, lo crea desde cero.
    """
    hoy = date.today()
    hoy_str = hoy.strftime("%Y%m%d")

    # Crear histórico si no existe
    if not os.path.exists("VENTAS_HISTORICO.DBF"):
        hist = Table(
            "VENTAS_HISTORICO.DBF",
            "EERR C(10); FECHA D; N_TICKET C(20); NOMBRES C(100); "
            "TIPO C(10); CANT N(12,2); P_UNIT N(12,2); "
            "CATEGORIA C(50); SUB_CAT C(50); COST_UNIT N(12,2); "
            "PRONUM C(20); DESCRI C(100)",
            codepage="cp850"
        )
        hist.open(mode=READ_WRITE)
        hist.close()

    # Abrir tablas originales
    cabecera = DBF("ZETH50T.DBF", load=True, encoding="latin-1")
    detalle = DBF("ZETH51T.DBF", load=True, encoding="latin-1")
    productos = DBF("ZETH70.DBF", load=True, encoding="latin-1")

    hist = Table("VENTAS_HISTORICO.DBF")
    hist.open(mode=READ_WRITE)

    # Cargar tickets ya existentes en el histórico
    tickets_existentes = {r["N_TICKET"] for r in hist}

    nuevos = 0
    for cab in cabecera:
        if str(cab["FECCHK"]) == hoy_str:
            n_ticket = cab["NUMCHK"]

            if n_ticket in tickets_existentes:
                continue  # Ya existe en histórico, no se inserta

            nombre = cab["CUSNAM"]
            tipo = cab["TYPMOV"]
            eerr = str(hoy.year)  # Puedes personalizarlo si es otro cálculo

            # Buscar detalles del ticket
            for det in detalle:
                if det["NUMCHK"] == n_ticket:
                    pronum = det["PRONUM"]
                    cant = det["QTYPRO"]
                    p_unit = det["PRIPRO"]

                    # Buscar datos adicionales del producto
                    cat = subcat = ""
                    cost_unit = 0
                    for prod in productos:
                        if prod["PRONUM"] == pronum:
                            cat = prod["CATEGORIA"] if "CATEGORIA" in prod else ""
                            subcat = prod["SUB_CAT"] if "SUB_CAT" in prod else ""
                            cost_unit = prod["ULCOSREP"] if "ULCOSREP" in prod else 0

                    hist.append((
                        eerr, hoy, n_ticket, nombre, tipo, cant, p_unit,
                        cat, subcat, cost_unit, pronum, det["DESCRI"]
                    ))
                    nuevos += 1

    hist.close()
    return {"status": "ok", "msg": f"Histórico actualizado. Nuevos registros: {nuevos}"}








