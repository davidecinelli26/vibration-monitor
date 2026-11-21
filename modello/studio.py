"""Studio di fattibilità: a 1000 campioni al secondo, quali caratteristiche distinguono
motore sano, squilibrio e disallineamento nelle registrazioni MAFAULDA?

Avvio:  uv run python studio.py   (servono i dati: replay/scarica_dati.py)

La valutazione tiene da parte file interi (GroupKFold): finestre dello stesso file si
somigliano, e mescolarle tra addestramento e prova darebbe un punteggio falso.
"""
from pathlib import Path

import numpy as np
import scipy.signal
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DATI = Path(__file__).parent.parent / "replay" / "dati" / "mafaulda"
FS, N, PASSO = 1000, 1024, 512
BANDE = 16
CLASSI = ["normale", "squilibrio", "disallineamento"]
ASSI = {"assiale": 1, "radiale": 2, "tangenziale": 3}     # colonne dell'accelerometro interno (underhang)


def classe(nome: str) -> int:
    if nome.startswith("normal"):
        return 0
    if nome.startswith("imbalance"):
        return 1
    return 2


def finestre(x: np.ndarray) -> np.ndarray:
    y = scipy.signal.resample_poly(x - x.mean(), FS, 51200)
    return np.stack([y[i:i + N] for i in range(0, len(y) - N + 1, PASSO)])


def come_il_firmware(w: np.ndarray) -> np.ndarray:
    """RMS, frequenza e ampiezza del picco: quello che l'ESP32 manda oggi."""
    y = w - w.mean()
    amp = np.abs(np.fft.rfft(y)) * 2 / N
    k = 1 + np.argmax(amp[1:])
    return np.array([np.sqrt(np.mean(y * y)), k * FS / N, amp[k]])


def energia_bande(w: np.ndarray) -> np.ndarray:
    """log dell'energia in BANDE bande uguali tra 0 e 500 Hz, con finestra di Hann, più log RMS."""
    y = w - w.mean()
    potenza = np.abs(np.fft.rfft(y * np.hanning(N))) ** 2
    bande = potenza[1:N // 2 + 1].reshape(BANDE, -1).sum(axis=1)
    return np.log10(np.concatenate([bande, [np.mean(y * y)]]) + 1e-12)


def carica():
    file = sorted(DATI.glob("*.csv"))
    X = {"firmware attuale (radiale)": [], "bande, solo radiale": [], "bande, 3 assi": []}
    y, gruppi = [], []
    for i, f in enumerate(file):
        dati = np.loadtxt(f, delimiter=",", usecols=list(ASSI.values()))
        per_asse = {a: finestre(dati[:, j]) for j, a in enumerate(ASSI)}
        for k in range(len(per_asse["radiale"])):
            X["firmware attuale (radiale)"].append(come_il_firmware(per_asse["radiale"][k]))
            X["bande, solo radiale"].append(energia_bande(per_asse["radiale"][k]))
            X["bande, 3 assi"].append(np.concatenate([energia_bande(per_asse[a][k]) for a in ASSI]))
            y.append(classe(f.name))
            gruppi.append(i)
    return {k: np.array(v) for k, v in X.items()}, np.array(y), np.array(gruppi), len(file)


def main() -> None:
    X, y, gruppi, n_file = carica()
    print(f"{n_file} file, {len(y)} finestre; per classe: "
          + ", ".join(f"{c} {np.sum(y == i)}" for i, c in enumerate(CLASSI)))
    for nome, Xs in X.items():
        previsto = np.empty_like(y)
        for addestra, prova in GroupKFold(n_splits=4).split(Xs, y, gruppi):
            m = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000))
            m.fit(Xs[addestra], y[addestra])
            previsto[prova] = m.predict(Xs[prova])
        print(f"\n{nome}: {Xs.shape[1]} numeri per finestra, "
              f"accuratezza bilanciata {balanced_accuracy_score(y, previsto):.2f}")
        print("  righe = vero, colonne = previsto:", " / ".join(CLASSI))
        for c, riga in zip(CLASSI, confusion_matrix(y, previsto)):
            print(f"  {c:<16} {riga}")


if __name__ == "__main__":
    main()
