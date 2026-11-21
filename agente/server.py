"""Server MCP: dà a un modello linguistico strumenti in sola lettura sulle misure di vibrazione.

Avvio (lo fa il client MCP, non tu):  uv run python server.py
"""
import os
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from mcp.server.mcpserver import MCPServer

# utente "agente": solo SELECT, transazioni in sola lettura, 5 s al massimo per query (vedi infra/db/schema.sql)
DB_URL = os.getenv("DB_URL", "postgresql://agente:agente@127.0.0.1:5432/vibrazioni")

ISTRUZIONI = """\
Sei un tecnico di manutenzione. Hai le misure di vibrazione di alcune macchine, una ogni secondo circa:
rms_g (vibrazione complessiva), picco_hz e picco_g (frequenza e ampiezza del componente più forte,
null se sotto 0,02 g). Il sensore vede solo le frequenze sotto 500 Hz.

Come leggere i dati:
- Le macchine "mafaulda-*" e "motore-1" girano a circa 29,5 giri al secondo. Un picco vicino a 29,5 Hz
  che cresce insieme all'RMS è il segno tipico di uno squilibrio.
- Il disallineamento NON si distingue da una macchina sana con questi dati: se lo sospetti, dillo
  e spiega che serve un'analisi diversa.
- I guasti ai cuscinetti delle macchine "cwru-*" sono quasi invisibili sotto 500 Hz: non trarre
  conclusioni dalle loro piccole differenze.
- "persi" o "saltati" maggiori di 0 vogliono dire che il sensore ha perso campioni: i dati di quel periodo
  sono meno affidabili.

Rispondi in italiano. Cita sempre i numeri su cui ti basi e gli orari. Se i dati non bastano, dillo.
"""

server = MCPServer("vibrazioni", instructions=ISTRUZIONI)
conn = None   # aperta al primo uso; i test la sostituiscono con la loro


def righe(sql: str, parametri: dict | None = None) -> list[dict]:
    global conn
    if conn is None:
        conn = psycopg.connect(DB_URL, autocommit=True)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, parametri or {})
        risultato = cur.fetchall()
    # date e numeri del database in forme che il JSON sa scrivere
    return [
        {k: v.isoformat(timespec="seconds") if isinstance(v, datetime) else
            round(v, 4) if isinstance(v, float) else v
         for k, v in r.items()}
        for r in risultato
    ]


@server.tool()
def elenca_dispositivi() -> list[dict]:
    """Elenca le macchine che hanno mandato misure, con quante misure e la prima e l'ultima."""
    return righe("""
        SELECT dispositivo, count(*) AS misure, min(ts) AS prima, max(ts) AS ultima
        FROM misure GROUP BY dispositivo ORDER BY dispositivo
    """)


@server.tool()
def stato(dispositivo: str, minuti: int = 10) -> list[dict]:
    """Andamento di una macchina negli ultimi `minuti`, un valore medio per minuto:
    rms_g, picco_hz, picco_g, e quanti campioni il sensore ha perso."""
    return righe("""
        SELECT time_bucket('1 minute', ts) AS minuto,
               count(*) AS misure,
               avg(rms_g) AS rms_g, avg(picco_hz) AS picco_hz, avg(picco_g) AS picco_g,
               max(persi) AS persi, max(saltati) AS saltati
        FROM misure
        WHERE dispositivo = %(dispositivo)s AND ts > now() - make_interval(mins => %(minuti)s)
        GROUP BY minuto ORDER BY minuto
    """, {"dispositivo": dispositivo, "minuti": minuti})


QUERY_ANOMALIE = """
    WITH ora AS (
        SELECT dispositivo, avg(rms_g) AS rms_ora, avg(picco_hz) AS picco_hz_ora
        FROM misure
        WHERE ts > now() - make_interval(mins => %(minuti)s)
        GROUP BY dispositivo
    ), prima AS (
        SELECT dispositivo, avg(rms_g) AS rms_prima, avg(picco_hz) AS picco_hz_prima
        FROM misure
        WHERE ts <= now() - make_interval(mins => %(minuti)s) AND ts > now() - make_interval(mins => %(minuti)s + 60)
        GROUP BY dispositivo
    )
    SELECT o.dispositivo, p.rms_prima, o.rms_ora, o.rms_ora / p.rms_prima AS rapporto, p.picco_hz_prima, o.picco_hz_ora
    FROM ora o
    JOIN prima p ON o.dispositivo = p.dispositivo
    WHERE o.rms_ora >= %(soglia)s * p.rms_prima
    ORDER BY rapporto DESC
"""


@server.tool()
def anomalie(minuti: int = 5, soglia: float = 1.5) -> list[dict]:
    """Macchine che negli ultimi `minuti` vibrano almeno `soglia` volte più della loro ora precedente."""
    return righe(QUERY_ANOMALIE, {"minuti": minuti, "soglia": soglia})


if __name__ == "__main__":
    server.run()   # stdio: il client avvia questo programma e gli parla da standard input/output
