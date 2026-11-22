"""Riceve le misure dal broker MQTT e le salva nella tabella `misure` di TimescaleDB.

Avvio:  python ingestor.py
"""
import json
import os

import paho.mqtt.client as mqtt
import psycopg

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORTA = int(os.getenv("MQTT_PORTA", "1883"))
TOPIC = "vibrazioni/#"
DB_URL = os.getenv("DB_URL", "postgresql://vibrazioni:vibrazioni@localhost:5432/vibrazioni")

INSERISCI = """
    INSERT INTO misure (dispositivo, rms_g, picco_hz, picco_g, persi, saltati, classe, confidenza)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def riga_da_messaggio(testo: bytes) -> tuple | None:
    """Trasforma il JSON dell'ESP32 nella tupla da inserire, nell'ordine di INSERISCI.

    Restituisce None se il messaggio non è valido (così un messaggio rotto
    non ferma il programma: lo si scarta e si va avanti).

    Esempio:
      b'{"dispositivo":"esp32-1","rms_g":0.21,"picco_hz":49.8,"picco_g":0.28,"persi":0,"saltati":0,
         "classe":"normale","confidenza":0.97}'
      -> ("esp32-1", 0.21, 49.8, 0.28, 0, 0, "normale", 0.97)

    classe e confidenza possono mancare (firmware precedente al classificatore): diventano None.
    """

    try:
        json_data = json.loads(testo)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    
    if not isinstance(json_data, dict):
        return None

    dispositivo = json_data.get("dispositivo")
    rms_g = json_data.get("rms_g")
    picco_hz = json_data.get("picco_hz")
    picco_g = json_data.get("picco_g")
    persi = json_data.get("persi")
    saltati = json_data.get("saltati")
    classe = json_data.get("classe")
    confidenza = json_data.get("confidenza")

    if None in (dispositivo, rms_g, persi, saltati):
        return None

    return (dispositivo, rms_g, picco_hz, picco_g, persi, saltati, classe, confidenza)


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
