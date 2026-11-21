"""Misura l'agente: domande fisse su uno scenario fisso, e controlli su cosa la risposta deve contenere.

Avvio:  uv run python valutazione.py

Lo scenario sta in un database a parte (vibrazioni_eval), ricreato a ogni avvio con orari relativi
a "adesso": il database delle misure vere non viene toccato, e i risultati si possono confrontare
tra un avvio e l'altro, cambiando istruzioni o modello.
"""
import asyncio
import contextlib
import io
import os
import re
import sys
import time

import psycopg

ADMIN_URL = os.getenv("ADMIN_URL", "postgresql://vibrazioni:vibrazioni@127.0.0.1:5432/vibrazioni")
DB_EVAL = "vibrazioni_eval"
URL_EVAL_ADMIN = ADMIN_URL.rsplit("/", 1)[0] + "/" + DB_EVAL
URL_EVAL_AGENTE = f"postgresql://agente:agente@127.0.0.1:5432/{DB_EVAL}"

# (dispositivo, rms_g, picco_hz, picco_g) da 65 a 5 minuti fa, e poi negli ultimi 5 minuti.
# motore-1 sviluppa uno squilibrio: RMS da 0,168 a 0,52 con il picco fermo a circa 29,5 Hz
# (valori misurati sulle registrazioni MAFAULDA). Le altre macchine non cambiano.
SCENARIO = [
    ("motore-1",                      (0.168, 29.3, 0.150), (0.520, 29.3, 0.665)),
    ("mafaulda-normale",              (0.168, 29.3, 0.150), (0.168, 29.3, 0.150)),
    ("mafaulda-disallineamento-oriz", (0.136, 29.3, 0.140), (0.136, 29.3, 0.140)),
    ("cwru-anello-interno",           (0.026, None, None),  (0.026, None, None)),
    ("cwru-normale",                  (0.021, None, None),  (0.021, None, None)),
]

# (domanda, controlli). Un controllo è (descrizione, espressione regolare, deve_esserci).
# Le regole valgono su testo minuscolo; "strumenti" sono le chiamate stampate dall'agente.
DOMANDE = [
    ("C'è qualche macchina che si sta comportando in modo strano?", [
        ("usa lo strumento anomalie", r"→ anomalie", True),
        ("indica motore-1", r"motore-1", True),
        ("parla di squilibrio", r"squilibri", True),
        ("non accusa la macchina sana", r"mafaulda-normale", False),
    ]),
    ("Il motore-1 ha un problema di disallineamento?", [
        ("dice che il disallineamento non si può stabilire",
         r"non\b.{0,60}(distingu|stabilir|determinar|possibile|può|riconosc)", True),
        ("non conclude 'squilibrio o disallineamento'", r"squilibrio o (un )?disallineamento", False),
    ]),
    ("Da quando il motore-1 vibra di più, e quanto?", [
        ("cita l'RMS di prima (circa 0,17)", r"0[.,]1[67]", True),
        ("cita l'RMS di adesso (circa 0,52)", r"0[.,]5[12]", True),
        ("cita un orario", r"\b\d{1,2}:\d{2}\b", True),
    ]),
    ("La macchina mafaulda-normale ha qualche problema?", [
        ("dice che è regolare", r"(nessun|non (ha|presenta|mostra|risulta|sembra)|regolar|stabil|normale)", True),
        ("non le attribuisce uno squilibrio", r"mafaulda-normale[^.]{0,80}squilibri", False),
        ("non esclude un disallineamento (non si può sapere)",
         r"non (presenta|ha|mostra)[^.]{0,40}disallineamento", False),
    ]),
    ("Le macchine cwru hanno guasti ai cuscinetti?", [
        ("spiega che sotto 500 Hz non si vedono",
         r"(500 ?hz|invisibil|non .{0,40}(vede|visibil|possibile|si può|rilev))", True),
    ]),
    ("Quali macchine ci sono?", [
        (f"nomina {d}", re.escape(d), True) for d, _, _ in SCENARIO
    ]),
]

# Su tutte le risposte: frequenze con più decimali di quanti la FFT ne possa dare (risoluzione ~1 Hz).
PRECISIONE_FINTA = ("niente frequenze con 3+ decimali", r"\d+[.,]\d{3,} ?hz", False)


def prepara_scenario() -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB_EVAL}")
        admin.execute(f"CREATE DATABASE {DB_EVAL}")
    with psycopg.connect(URL_EVAL_ADMIN, autocommit=True) as db:
        db.execute("""
            CREATE TABLE misure (
                ts timestamptz NOT NULL, dispositivo text NOT NULL, rms_g real NOT NULL,
                picco_hz real, picco_g real, persi integer NOT NULL, saltati integer NOT NULL)""")
        db.execute("GRANT SELECT ON misure TO agente")
        with db.cursor() as cur:
            for dispositivo, prima, ora in SCENARIO:
                righe = [(s, dispositivo, *(ora if s < 300 else prima))
                         for s in range(0, 65 * 60, 10)]          # una misura ogni 10 s, per 65 minuti
                cur.executemany(
                    "INSERT INTO misure VALUES (now() - %s * interval '1 second', %s, %s, %s, %s, 0, 0)", righe)


async def chiedi(domanda: str) -> str:
    """Risposta dell'agente più le chiamate agli strumenti che stampa."""
    from agente import rispondi
    stampa = io.StringIO()
    with contextlib.redirect_stdout(stampa):
        risposta = await rispondi(domanda)
    return stampa.getvalue() + "\n" + (risposta or "")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    prepara_scenario()
    os.environ["DB_URL"] = URL_EVAL_AGENTE

    superati = totali = 0
    for domanda, controlli in DOMANDE:
        inizio = time.time()
        testo = asyncio.run(chiedi(domanda))
        print(f"\n### {domanda}  ({time.time() - inizio:.0f} s)\n{testo.strip()}\n")
        for descrizione, regola, deve_esserci in controlli + [PRECISIONE_FINTA]:
            ok = bool(re.search(regola, testo.lower())) == deve_esserci
            superati += ok
            totali += 1
            print(f"  {'OK  ' if ok else 'NO  '} {descrizione}")
    print(f"\nPunteggio: {superati}/{totali} controlli superati")


if __name__ == "__main__":
    main()
