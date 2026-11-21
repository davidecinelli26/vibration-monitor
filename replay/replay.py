"""Riproduce le registrazioni CWRU come se fossero ESP32: stesso calcolo, stesso JSON, stesso topic.

Avvio:  uv run python replay.py
I file .mat vanno in dati/ (non sono nel repository: si scaricano da engineering.case.edu).
"""
import json
import os
import time
from pathlib import Path

import numpy as np
import paho.mqtt.client as mqtt
import scipy.io
import scipy.signal

FS = 1000                 # come l'MPU-6050: 1000 campioni al secondo
N = 1024                  # campioni per finestra, come il firmware
SOGLIA_PICCO_G = 0.02     # come SOGLIA_PICCO_G nel firmware
DATI = Path(__file__).parent / "dati"
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORTA = int(os.getenv("MQTT_PORTA", "1883"))

# (dispositivo, file in dati/, campioni al secondo originali)
REGISTRAZIONI = [
    # CWRU: 0 HP, circa 1797 giri/min, guasti da 0,007 pollici, accelerometro lato motore (DE).
    # Il "sano" è registrato a 48 kHz, gli altri a 12 kHz.
    ("cwru-normale",        "97.mat",  48000),
    ("cwru-anello-interno", "105.mat", 12000),
    ("cwru-sfera",          "118.mat", 12000),
    ("cwru-anello-esterno", "130.mat", 12000),
    # MAFAULDA: tutti a circa 29,5 giri al secondo (il nome del file è la velocità in Hz).
    # Il sito dice 50 kHz, ma i nomi dei file tornano con gli impulsi del tachimetro solo a 51,2 kHz,
    # che è anche la frequenza della scheda NI 9234 usata per registrarli.
    ("mafaulda-normale",              "mafaulda/normal__29.4912.csv",                       51200),
    ("mafaulda-squilibrio-6g",        "mafaulda/imbalance__6g__29.4912.csv",                51200),
    ("mafaulda-squilibrio-20g",       "mafaulda/imbalance__20g__29.4912.csv",               51200),
    ("mafaulda-squilibrio-35g",       "mafaulda/imbalance__35g__29.9008.csv",               51200),
    ("mafaulda-disallineamento-oriz", "mafaulda/horizontal-misalignment__2.0mm__29.0816.csv", 51200),
    ("mafaulda-disallineamento-vert", "mafaulda/vertical-misalignment__1.90mm__29.9008.csv",  51200),
]


# motore-1: una macchina che si guasta mentre la guardi. Parte sana e ogni FASE_FINESTRE
# finestre (circa 2 minuti) passa alla registrazione successiva; poi resta sull'ultima.
SCENARIO_MOTORE_1 = ["mafaulda-normale", "mafaulda-squilibrio-6g", "mafaulda-squilibrio-20g", "mafaulda-squilibrio-35g"]
FASE_FINESTRE = 120


def fase_motore_1(i: int) -> str:
    """La registrazione che motore-1 riproduce alla finestra numero i."""
    return SCENARIO_MOTORE_1[min(i // FASE_FINESTRE, len(SCENARIO_MOTORE_1) - 1)]


def carica(percorso: Path, fs_originale: int) -> np.ndarray:
    """Legge un accelerometro della registrazione e lo porta a FS campioni al secondo."""
    if percorso.suffix == ".csv":
        # MAFAULDA, colonna 3: accelerometro radiale del cuscinetto interno (underhang).
        # Il sito non dice l'unità (g o volt): usiamo i valori così come sono.
        x = np.loadtxt(percorso, delimiter=",", usecols=2)
    else:
        mat = scipy.io.loadmat(percorso)
        chiave = next(k for k in mat if k.endswith("_DE_time"))   # CWRU, in g
        x = mat[chiave].ravel()
    # resample_poly filtra prima le frequenze sopra 500 Hz, poi riduce i campioni (FS/fs_originale):
    # senza filtro quelle frequenze si "ripiegherebbero" sotto i 500 Hz (aliasing)
    return scipy.signal.resample_poly(x, FS, fs_originale)


def analizza(x: np.ndarray) -> tuple[float, float, float]:
    """Lo stesso calcolo del firmware su una finestra di N campioni.

    Restituisce (rms_g, picco_hz, picco_g):
      rms_g     RMS dopo aver tolto la media
      picco_hz  frequenza del bin più alto, escluso il bin 0
      picco_g   ampiezza di quel bin

    Esempio: sinusoide 50 Hz, 0,3 g, più 1 g di gravità -> (0.2121, 49.8, 0.28 circa)
    """
    
    y = x - x.mean()
    rms = np.sqrt(np.mean(y ** 2))
    amp = np.abs(np.fft.rfft(y)) * 2 / len(y)
    k = 1 + np.argmax(amp[1:])
    return float(rms), float(k * FS / len(y)), float(amp[k])


def messaggio(dispositivo: str, rms_g: float, picco_hz: float, picco_g: float) -> str:
    """Lo stesso JSON di componi_messaggio() nel firmware."""
    sopra = picco_g >= SOGLIA_PICCO_G
    return json.dumps({
        "dispositivo": dispositivo,
        "rms_g": round(rms_g, 4),
        "picco_hz": round(picco_hz, 1) if sopra else None,
        "picco_g": round(picco_g, 4) if sopra else None,
        "persi": 0,
        "saltati": 0,
    })


def main() -> None:
    finestre = {}
    for dispositivo, nome, fs in REGISTRAZIONI:
        x = carica(DATI / nome, fs)
        finestre[dispositivo] = [x[i:i + N] for i in range(0, len(x) - N + 1, N)]
        print(f"{dispositivo}: {len(finestre[dispositivo])} finestre da {nome}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, MQTT_PORTA)
    client.loop_start()

    i = 0
    while True:     # finite le finestre ricomincia da capo, come un sensore sempre acceso
        sorgenti = {**finestre, "motore-1": finestre[fase_motore_1(i)]}
        for dispositivo, lista in sorgenti.items():
            testo = messaggio(dispositivo, *analizza(lista[i % len(lista)]))
            client.publish(f"vibrazioni/{dispositivo}", testo)
            print(testo)
        i += 1
        time.sleep(N / FS)   # una finestra ogni 1,024 s, come in tempo reale


if __name__ == "__main__":
    main()
