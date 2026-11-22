"""Server MCP: dà a un modello linguistico strumenti in sola lettura sulle misure di vibrazione.

Non si avvia a mano: lo lancia agente.py come sottoprocesso e gli parla via stdio.
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
null se sotto 0,02 g), e classe: cosa dice un classificatore che gira sulla scheda ("normale",
"squilibrio", "disallineamento" o "sconosciuta"). Il sensore vede solo le frequenze sotto 500 Hz.

Come leggere i dati:
- Le frequenze hanno una risoluzione di circa 1 Hz: 29,3 Hz e 30,3 Hz vanno letti come "circa 29,5 Hz".
- Le macchine "mafaulda-*" e "motore-1" girano a circa 29,5 giri al secondo. Se l'RMS cresce e il picco
  resta vicino a 29,5 Hz, la causa più probabile è uno squilibrio: dillo con questa parola.
- Il disallineamento si vede solo dalla classe, non da RMS e picco. Se la classe è "disallineamento",
  presentalo come un sospetto da verificare con un controllo, non come una certezza.
- Classe "sconosciuta": il classificatore non si pronuncia, e nemmeno tu.
- I guasti ai cuscinetti delle macchine "cwru-*" sono quasi invisibili sotto 500 Hz: non trarre
  conclusioni dalle loro piccole differenze.
- "persi" o "saltati" maggiori di 0 vogliono dire che il sensore ha perso campioni: i dati di quel periodo
  sono meno affidabili.

Come procedere, secondo la domanda:
- "Quali macchine ci sono?": chiama `elenca_dispositivi` e nominale tutte.
- Una domanda sui sensori o sull'affidabilità dei dati: chiama `sensori`.
- Una domanda generale ("qualcosa non va?"): chiama `anomalie` (confronta gli ultimi 5 minuti con
  l'ora prima), poi `stato` sulle macchine che segnala. Se non segnala nulla, dillo.
- Una domanda su una macchina precisa: chiama `stato` su quella macchina con minuti=60 e guarda
  quando e quanto è cambiato l'RMS.
- Una domanda su un tipo di guasto: prima di guardare i dati, controlla nelle regole qui sopra se
  quel guasto si può vedere con questo sensore. Se non si può, dillo come prima cosa.
Rispondi solo alla domanda fatta. Usa gli strumenti senza chiedere il permesso.

Rispondi in italiano, in poche frasi. Cita i numeri su cui ti basi e gli orari. Se i dati non bastano, dillo.
"""

server = MCPServer("vibrazioni", instructions=ISTRUZIONI)
conn = None   # aperta al primo uso; i test la sostituiscono con la loro


def righe(sql: str, parametri: dict | None = None) -> list[dict]:
    global conn
    if conn is None:
        conn = psycopg.connect(DB_URL, autocommit=True, options="-c TimeZone=Europe/Rome")   # orari italiani
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
    """Elenca le macchine che hanno mandato misure: quante misure, la prima, l'ultima e l'ultima classe."""
    return righe("""
        SELECT dispositivo, count(*) AS misure, min(ts) AS prima, max(ts) AS ultima,
               (array_agg(classe ORDER BY ts DESC))[1] AS classe
        FROM misure GROUP BY dispositivo ORDER BY dispositivo
    """)


@server.tool()
def stato(dispositivo: str, minuti: int = 10) -> list[dict]:
    """Andamento di una macchina negli ultimi `minuti`, in al massimo 12 intervalli:
    per ognuno rms_g, picco_hz, picco_g medi, la classe più frequente e quanti campioni il sensore ha perso."""
    # al massimo 12 righe: un risultato lungo riempirebbe il contesto del modello e gli farebbe
    # perdere le istruzioni
    return righe("""
        SELECT time_bucket(make_interval(mins => %(passo)s), ts) AS da,
               count(*) AS misure,
               avg(rms_g) AS rms_g, avg(picco_hz) AS picco_hz, avg(picco_g) AS picco_g,
               mode() WITHIN GROUP (ORDER BY classe) AS classe,
               max(persi) AS persi, max(saltati) AS saltati
        FROM misure
        WHERE dispositivo = %(dispositivo)s AND ts > now() - make_interval(mins => %(minuti)s)
        GROUP BY da ORDER BY da
    """, {"dispositivo": dispositivo, "minuti": minuti, "passo": max(1, -(-minuti // 12))})


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
    SELECT o.dispositivo, p.rms_prima, o.rms_ora, o.rms_ora / NULLIF(p.rms_prima, 0) AS rapporto, p.picco_hz_prima, o.picco_hz_ora
    FROM ora o
    JOIN prima p ON o.dispositivo = p.dispositivo
    WHERE o.rms_ora >= %(soglia)s * p.rms_prima
    ORDER BY rapporto DESC
"""


def trova_anomalie(minuti: int, soglia: float) -> list[dict]:
    return righe(QUERY_ANOMALIE, {"minuti": minuti, "soglia": soglia})


@server.tool()
def anomalie() -> list[dict]:
    """Macchine che negli ultimi 5 minuti vibrano almeno 1,5 volte più della loro ora precedente."""
    # parametri fissi: quando poteva sceglierli, il modello usava 60 minuti e il confronto non trovava nulla
    return trova_anomalie(minuti=5, soglia=1.5)


@server.tool()
def sensori() -> list[dict]:
    """Macchine il cui sensore ha perso campioni nell'ultima ora: quanti persi e saltati, e da quando.
    Lista vuota: nessun sensore ha perso campioni."""
    # persi e saltati sono contatori che il firmware non azzera: conta quanto sono cresciuti
    return righe("""
        SELECT dispositivo,
               max(persi) - min(persi) AS persi, max(saltati) - min(saltati) AS saltati,
               min(ts) FILTER (WHERE persi > m.persi_min OR saltati > m.saltati_min) AS da
        FROM misure
        JOIN (SELECT dispositivo, min(persi) AS persi_min, min(saltati) AS saltati_min
              FROM misure WHERE ts > now() - interval '60 minutes' GROUP BY dispositivo) m USING (dispositivo)
        WHERE ts > now() - interval '60 minutes'
        GROUP BY dispositivo
        HAVING max(persi) > min(persi) OR max(saltati) > min(saltati)
        ORDER BY persi DESC
    """)


if __name__ == "__main__":
    server.run()   # stdio: il client avvia questo programma e gli parla da standard input/output
