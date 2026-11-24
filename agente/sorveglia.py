"""Sorveglia le macchine e avvisa su Telegram quando qualcosa cambia.

Avvio:  uv run --env-file .env python sorveglia.py

Ogni OGNI_SECONDI controlla le anomalie di vibrazione e i sensori che perdono campioni, con le
stesse query degli strumenti MCP. Decidere se avvisare è compito di queste query, non del modello:
una soglia sbaglia sempre allo stesso modo, un modello no, e chiamarlo ogni minuto costerebbe.
Il modello entra solo quando c'è qualcosa da dire: riceve le segnalazioni, usa gli strumenti per
guardare meglio e scrive il messaggio. Se non risponde, parte comunque un avviso con i numeri.

Variabili (in agente/.env):
  TELEGRAM_TOKEN    il token del bot, da @BotFather
  TELEGRAM_CHAT_ID  la chat a cui scrivere
Senza le due variabili i messaggi vengono solo stampati: utile per provare.
"""
import asyncio
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import server
from agente import rispondi

OGNI_SECONDI = int(os.getenv("OGNI_SECONDI", "60"))
PAUSA_SECONDI = int(os.getenv("PAUSA_SECONDI", "3600"))   # la stessa segnalazione al massimo una volta all'ora
MAX_CARATTERI = 4096                                       # limite di Telegram per un messaggio


def segnalazioni() -> dict[str, dict]:
    """Cosa c'è da segnalare adesso, per chiave: "anomalia:<macchina>" o "sensore:<macchina>"."""
    trovate = {f"anomalia:{r['dispositivo']}": r for r in server.trova_anomalie(minuti=5, soglia=1.5)}
    trovate |= {f"sensore:{r['dispositivo']}": r for r in server.sensori()}
    return trovate


def da_avvisare(chiavi: list[str], ultimi_avvisi: dict[str, float], adesso: float, pausa: float) -> list[str]:
    """Le chiavi da avvisare adesso: quelle mai avvisate, o avvisate più di `pausa` secondi fa.

    ultimi_avvisi: per ogni chiave, quando (time.time()) è partito l'ultimo avviso.
    L'ordine di `chiavi` va mantenuto.
    """
    return [k for k in chiavi if adesso - ultimi_avvisi.get(k, float("-inf")) > pausa]


def messaggio_di_riserva(nuove: dict[str, dict]) -> str:
    """L'avviso senza modello: i numeri delle query, una riga per segnalazione."""
    return "Avviso vibrazioni\n" + "\n".join(f"- {k}: {json.dumps(r, ensure_ascii=False)}" for k, r in nuove.items())


async def spiega(nuove: dict[str, dict]) -> str:
    domanda = (
        "Avviso automatico, nessuno ha fatto domande. Il controllo periodico ha trovato queste "
        f"segnalazioni: {json.dumps(nuove, ensure_ascii=False)}. "
        "Guarda le macchine coinvolte con gli strumenti e scrivi l'avviso per il tecnico: cosa succede, "
        "da quando, e cosa conviene fare. Al massimo cinque frasi."
    )
    return await rispondi(domanda)


def invia(testo: str) -> None:
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print(f"(prova, niente Telegram)\n{testo}\n")
        return
    testo = testo.replace("**", "")[:MAX_CARATTERI]       # i modelli scrivono in Markdown, qui va testo semplice
    dati = urllib.parse.urlencode({"chat_id": chat, "text": testo}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dati, timeout=10) as r:
        if not json.load(r).get("ok"):
            raise RuntimeError("Telegram ha rifiutato il messaggio")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ultimi_avvisi: dict[str, float] = {}
    print(f"sorveglio ogni {OGNI_SECONDI} s")
    while True:
        trovate = segnalazioni()
        nuove = {k: trovate[k] for k in da_avvisare(list(trovate), ultimi_avvisi, time.time(), PAUSA_SECONDI)}
        if nuove:
            try:
                testo = asyncio.run(spiega(nuove))
            except Exception as e:      # modello spento o servizio in rete che non risponde
                print(f"modello non disponibile ({type(e).__name__}), mando i numeri")
                testo = messaggio_di_riserva(nuove)
            try:
                invia(testo)
                ultimi_avvisi |= dict.fromkeys(nuove, time.time())
            except Exception as e:      # rete giù: si riprova al prossimo giro
                print(f"invio fallito: {e}")
        time.sleep(OGNI_SECONDI)


if __name__ == "__main__":
    main()
