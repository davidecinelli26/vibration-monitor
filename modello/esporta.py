"""Addestra il classificatore su tutte le finestre MAFAULDA e lo scrive come tabelle C per il firmware.

Avvio:  uv run python esporta.py   (servono i dati: replay/scarica_dati.py)

Scrive:
  firmware/lib/classificatore/modello.h               normalizzazione, pesi e nomi delle classi
  firmware/test/test_classificatore/esempi.h           una finestra per classe, con caratteristiche e
                                                       probabilità calcolate qui, per i test del firmware
"""
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from studio import CLASSI, DATI, carica, energia_bande, finestre

FIRMWARE = Path(__file__).parent.parent / "firmware"
# Oltre LIMITE deviazioni standard da quello visto in addestramento, la finestra non somiglia
# a MAFAULDA e il modello direbbe una classe a caso con sicurezza: si risponde "sconosciuta".
# In addestramento si arriva al massimo a 5; CWRU e la sinusoide di Wokwi stanno tra 13 e 64.
LIMITE = 6.0


def c(v) -> str:
    """Numeri come inizializzatore C: {1.5f, -2f, ...}, anche annidati."""
    if np.ndim(v) == 0:
        return f"{float(v):.8e}f"
    return "{" + ", ".join(c(x) for x in v) + "}"


def main() -> None:
    X, y, _, _ = carica()
    X = X["bande, solo radiale"]
    modello = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000))
    modello.fit(X, y)
    scala, logistica = modello.named_steps.values()

    # il firmware calcola softmax(PESI · (x - MEDIA) / SCALA + BIAS): deve dare le stesse probabilità
    z = (X - scala.mean_) / scala.scale_ @ logistica.coef_.T + logistica.intercept_
    p = np.exp(z - z.max(axis=1, keepdims=True))
    assert np.allclose(p / p.sum(axis=1, keepdims=True), modello.predict_proba(X))
    print(f"accuratezza sulle finestre di addestramento: {np.mean(modello.predict(X) == y):.3f}")
    distanza = np.abs((X - scala.mean_) / scala.scale_).max(axis=1).max()
    assert distanza < LIMITE, distanza
    print(f"distanza massima in addestramento: {distanza:.1f} deviazioni standard (limite {LIMITE})")

    n_car, n_classi = X.shape[1], len(CLASSI)
    (FIRMWARE / "lib" / "classificatore" / "modello.h").write_text(f"""\
#pragma once
/* Generato da modello/esporta.py: non modificare a mano. */

#define N_CARATTERISTICHE {n_car}
#define N_CLASSI {n_classi}
#define SCONOSCIUTA N_CLASSI
#define LIMITE {c(LIMITE)}

static const char *const NOMI_CLASSI[N_CLASSI + 1] = {{{", ".join(f'"{n}"' for n in CLASSI)}, "sconosciuta"}};
static const float MEDIA[N_CARATTERISTICHE] = {c(scala.mean_)};
static const float SCALA[N_CARATTERISTICHE] = {c(scala.scale_)};
static const float PESI[N_CLASSI][N_CARATTERISTICHE] = {c(logistica.coef_)};
static const float BIAS[N_CLASSI] = {c(logistica.intercept_)};
""", encoding="utf-8")

    # una finestra per classe: la prima di ogni classe
    esempi = []
    for i, prefisso in enumerate(["normal", "imbalance", "horizontal"]):
        f = sorted(DATI.glob(f"{prefisso}*.csv"))[0]
        w = finestre(np.loadtxt(f, delimiter=",", usecols=2))[0]
        car = energia_bande(w)
        esempi.append((i, f.name, w, car, modello.predict_proba([car])[0]))
    blocchi = "\n".join(f"""\
    /* {nome} */
    {{{classe}, {c(w)},
     {c(car)},
     {c(prob)}}},""" for classe, nome, w, car, prob in esempi)
    (FIRMWARE / "test" / "test_classificatore" / "esempi.h").write_text(f"""\
#pragma once
/* Generato da modello/esporta.py: finestre MAFAULDA e quello che ne calcola il Python. */

struct Esempio {{
    int classe;
    float finestra[{len(esempi[0][2])}];
    float caratteristiche[{n_car}];
    float probabilita[{n_classi}];
}};

static const Esempio ESEMPI[] = {{
{blocchi}
}};
""", encoding="utf-8")
    print("scritti modello.h ed esempi.h")


if __name__ == "__main__":
    main()
