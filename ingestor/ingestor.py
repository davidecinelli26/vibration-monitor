"""Riceve le misure dal broker MQTT e le salva nella tabella `misure` di TimescaleDB.

Avvio:  uv run python ingestor.py
"""
import json
import os

import paho.mqtt.client as mqtt
import psycopg

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORTA = int(os.getenv("MQTT_PORTA", "1883"))
TOPIC = "vibrazioni/#"
DB_URL = os.getenv("DB_URL", "postgresql://vibrazioni:vibrazioni@127.0.0.1:5432/vibrazioni")

CAMPI = ("dispositivo", "rms_g", "picco_hz", "picco_g", "persi", "saltati", "classe", "confidenza")
OBBLIGATORI = ("dispositivo", "rms_g", "persi", "saltati")
INSERISCI = f"INSERT INTO misure ({', '.join(CAMPI)}) VALUES ({', '.join(['%s'] * len(CAMPI))})"


def riga_da_messaggio(testo: bytes) -> tuple | None:
    """Il JSON della scheda come tupla da inserire, nell'ordine di CAMPI.

    I campi che possono mancare (picco sotto soglia, firmware senza classificatore) diventano None.
    Un messaggio non valido dà None: si scarta e si va avanti, senza fermare il programma.

    Esempio:
      b'{"dispositivo":"esp32-1","rms_g":0.21,"picco_hz":49.8,"picco_g":0.28,"persi":0,"saltati":0,
         "classe":"normale","confidenza":0.97}'
      -> ("esp32-1", 0.21, 49.8, 0.28, 0, 0, "normale", 0.97)
    """
    try:
        dati = json.loads(testo)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(dati, dict) or any(dati.get(c) is None for c in OBBLIGATORI):
        return None
    return tuple(dati.get(c) for c in CAMPI)


def main() -> None:
    db = psycopg.connect(DB_URL, autocommit=True)   # autocommit: ogni INSERT è salvato subito

    def su_messaggio(client, userdata, msg):
        riga = riga_da_messaggio(msg.payload)
        if riga is None:
            print(f"scartato {msg.topic}: {msg.payload[:80]!r}")
            return
        try:
            db.execute(INSERISCI, riga)
        except psycopg.DataError as e:      # es. "rms_g":"abc": il JSON è valido ma il DB rifiuta il tipo
            print(f"scartato {msg.topic}: {e}")
            return
        print(f"salvato {riga}")

    def su_connessione(client, userdata, flags, reason_code, properties):
        print(f"MQTT collegato ({reason_code}), ascolto {TOPIC}")
        client.subscribe(TOPIC)    # qui e non prima: se la connessione cade, al ritorno ci si re-iscrive

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = su_connessione
    client.on_message = su_messaggio
    client.connect(MQTT_HOST, MQTT_PORTA)
    client.loop_forever()          # gestisce anche il ricollegamento


if __name__ == "__main__":
    main()
