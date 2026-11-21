"""Misura l'agente: domande fisse su uno scenario fisso, e controlli su cosa la risposta deve contenere.

Avvio:  uv run --env-file .env python valutazione.py [modello ...]
        (i nomi sono le chiavi di MODELLI; senza nomi usa qwen2.5-7b)

Lo scenario sta in un database a parte (vibrazioni_eval), ricreato per ogni modello con orari relativi
a "adesso": il database delle misure vere non viene toccato, e i risultati si possono confrontare
tra un avvio e l'altro, cambiando istruzioni o modello.

I modelli in rete vogliono una chiave, letta dalla variabile indicata in MODELLI. Con
`--env-file .env` uv le legge dal file agente/.env, che non va mai nel repository.
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

OLLAMA = "http://127.0.0.1:11434/v1"
GROQ = "https://api.groq.com/openai/v1"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"
# nome: (indirizzo, modello, variabile con la chiave)
MODELLI = {
    "qwen2.5-7b":    (OLLAMA, "qwen2.5:7b", None),
    "qwen3-8b":      (OLLAMA, "qwen3:8b", None),
    "granite3.3-8b": (OLLAMA, "granite3.3:8b", None),
    "llama3.1-8b":   (OLLAMA, "llama3.1:8b", None),
    # in rete, piani gratuiti (elenco di novembre 2026: i servizi cambiano spesso i modelli disponibili)
    "groq-gpt-oss-20b":  (GROQ, "openai/gpt-oss-20b", "GROQ_API_KEY"),
    "groq-gpt-oss-120b": (GROQ, "openai/gpt-oss-120b", "GROQ_API_KEY"),
    "groq-qwen3.8-27b":  (GROQ, "qwen/qwen3.8-27b", "GROQ_API_KEY"),
    "gemini-flash-lite": (GEMINI, "gemini-flash-lite-latest", "GEMINI_API_KEY"),
    "gemini-flash":      (GEMINI, "gemini-flash-latest", "GEMINI_API_KEY"),
}

# (dispositivo, (rms_g, picco_hz, picco_g, persi) da 65 a 5 minuti fa, lo stesso negli ultimi 5 minuti).
# motore-1 sviluppa uno squilibrio: RMS da 0,168 a 0,52 con il picco fermo a circa 29,5 Hz
# (valori misurati sulle registrazioni MAFAULDA). motore-2 vibra normalmente, ma il suo sensore
# comincia a perdere campioni. Le altre macchine non cambiano.
SCENARIO = [
    ("motore-1",                      (0.168, 29.3, 0.150, 0), (0.520, 29.3, 0.665, 0)),
    ("motore-2",                      (0.170, 29.3, 0.150, 0), (0.171, 29.3, 0.152, 37)),
    ("mafaulda-normale",              (0.168, 29.3, 0.150, 0), (0.168, 29.3, 0.150, 0)),
    ("mafaulda-disallineamento-oriz", (0.136, 29.3, 0.140, 0), (0.136, 29.3, 0.140, 0)),
    ("cwru-anello-interno",           (0.026, None, None, 0),  (0.026, None, None, 0)),
    ("cwru-normale",                  (0.021, None, None, 0),  (0.021, None, None, 0)),
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

# Domande mai usate per migliorare le istruzioni: il loro punteggio è quello onesto.
# Se le istruzioni vengono cambiate guardando queste risposte, servono domande nuove.
DOMANDE_NUOVE = [
    ("Quale macchina vibra di più in questo momento?", [
        ("indica motore-1", r"motore-1", True),
        ("cita il suo RMS (circa 0,52)", r"0[.,]5[12]", True),
    ]),
    ("Ci sono problemi con i sensori?", [
        ("indica motore-2", r"motore-2", True),
        ("parla di campioni persi", r"(pers|campion)", True),
    ]),
    ("Com'è messo il motore-9?", [
        ("dice che non ci sono dati",
         r"(non (esiste|risulta|trov|ci sono|ho|è present|compare|sono stat)|nessun[ao]? (dat|misur|macchin))", True),
        ("non inventa valori", r"0[.,]\d+ ?g", False),
    ]),
    ("Devo fermare il motore-1?", [
        ("parla di squilibrio", r"squilibri", True),
        ("consiglia un controllo", r"(controll|verific|ispezion|manutenzion|bilanci)", True),
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
                    "INSERT INTO misure VALUES (now() - %s * interval '1 second', %s, %s, %s, %s, %s, 0)", righe)


async def chiedi(domanda: str) -> str:
    """Risposta dell'agente più le chiamate agli strumenti che stampa."""
    from agente import rispondi
    stampa = io.StringIO()
    with contextlib.redirect_stdout(stampa):
        risposta = await rispondi(domanda)
    return stampa.getvalue() + "\n" + (risposta or "")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["DB_URL"] = URL_EVAL_AGENTE
    tabella = []
    for nome in sys.argv[1:] or ["qwen2.5-7b"]:
        url, modello, variabile_chiave = MODELLI[nome]
        if variabile_chiave and not os.getenv(variabile_chiave):
            print(f"\n{nome}: salto, manca la variabile {variabile_chiave}")
            continue
        os.environ.update(LLM_URL=url, LLM_MODELLO=modello,
                          LLM_CHIAVE=os.getenv(variabile_chiave or "", "ollama"))
        prepara_scenario()      # per ogni modello: gli orari sono relativi a "adesso"
        print(f"\n======== {nome} ========")
        inizio = time.time()
        usate, nuove = valuta(DOMANDE), valuta(DOMANDE_NUOVE)
        secondi = (time.time() - inizio) / (len(DOMANDE) + len(DOMANDE_NUOVE))
        tabella.append((nome, usate, nuove, secondi))

    print(f"\n{'modello':<20} {'domande usate':>14} {'domande nuove':>14} {'s/domanda':>10} {'errori':>7}")
    for nome, (u_ok, u_tot, u_err), (n_ok, n_tot, n_err), secondi in tabella:
        print(f"{nome:<20} {f'{u_ok}/{u_tot}':>14} {f'{n_ok}/{n_tot}':>14} {secondi:>10.0f} {u_err + n_err:>7}")


# alcuni modelli scrivono "motore‑1" con il trattino non divisibile, o usano spazi speciali
TRATTINI_E_SPAZI = str.maketrans({"‐": "-", "‑": "-", "–": "-", " ": " ", " ": " "})


def valuta(domande) -> tuple[int, int, int]:
    superati = totali = errori = 0
    for domanda, controlli in domande:
        inizio = time.time()
        try:
            testo = asyncio.run(chiedi(domanda)).translate(TRATTINI_E_SPAZI)
        except Exception as e:      # un modello che non sa usare gli strumenti non deve fermare il confronto
            while isinstance(e, BaseExceptionGroup) and e.exceptions:
                e = e.exceptions[0]                 # l'errore vero, non il contenitore di asyncio
            testo = f"ERRORE: {type(e).__name__}: {str(e)[:300]}"
            errori += 1
        print(f"\n### {domanda}  ({time.time() - inizio:.0f} s)\n{testo.strip()}\n")
        for descrizione, regola, deve_esserci in controlli + [PRECISIONE_FINTA]:
            ok = bool(re.search(regola, testo.lower())) == deve_esserci
            superati += ok
            totali += 1
            print(f"  {'OK  ' if ok else 'NO  '} {descrizione}")
    return superati, totali, errori


if __name__ == "__main__":
    main()
