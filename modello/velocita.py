"""Il classificatore regge fuori da 28-32 giri al secondo? Prova su tutte le registrazioni MAFAULDA.

Avvio:  uv run python velocita.py --scarica   (una volta: legge 5,8 GB, salva circa 30 MB)
        uv run python velocita.py

Il modello sulla scheda è addestrato su 72 registrazioni vicine a 30 giri al secondo, e le sane
sono solo 4. Qui si usano tutte le velocità (49 registrazioni sane) per due domande:
  1. il modello di oggi, su velocità che non ha mai visto, cosa risponde?
  2. addestrato su tutte le velocità, riconosce le classi a velocità tenute da parte?
"""
import sys
import tarfile
import urllib.request
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from esporta import LIMITE
from studio import ASSI, CLASSI, classe, energia_bande, finestre

CACHE = Path(__file__).parent.parent / "replay" / "dati" / "mafaulda_1khz"
MAFAULDA = "https://www02.smt.ufrj.br/~offshore/mfs/database/mafaulda/{}.tgz"
ARCHIVI = ("normal", "imbalance", "horizontal-misalignment", "vertical-misalignment")


def scarica() -> None:
    """Salva le finestre a 1 kHz dell'asse radiale di ogni registrazione, non i CSV interi."""
    CACHE.mkdir(parents=True, exist_ok=True)
    for archivio in ARCHIVI:
        print(f"leggo {archivio}.tgz")
        with urllib.request.urlopen(MAFAULDA.format(archivio)) as r, tarfile.open(fileobj=r, mode="r|gz") as tar:
            for m in tar:
                if not (m.isfile() and m.name.endswith(".csv")):
                    continue
                dest = CACHE / (m.name.replace("/", "__")[:-4] + ".npy")
                with tar.extractfile(m) as src:
                    x = np.loadtxt(src, delimiter=",", usecols=ASSI["radiale"])
                np.save(dest, finestre(x).astype(np.float32))


def carica():
    X, y, giri, file = [], [], [], []
    for i, f in enumerate(sorted(CACHE.glob("*.npy"))):
        hz = float(f.stem.split("__")[-1])
        for w in np.load(f):
            X.append(energia_bande(w))
            y.append(classe(f.name))
            giri.append(hz)
            file.append(i)
    return np.array(X), np.array(y), np.array(giri), np.array(file)


def nuovo_modello():
    return make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000))


def stampa_confusione(y, previsto, etichette):
    print("  righe = vero, colonne = previsto:", " / ".join(etichette))
    for c, riga in zip(CLASSI, confusion_matrix(y, previsto, labels=range(len(etichette)))[:len(CLASSI)]):
        print(f"  {c:<16} {riga}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if "--scarica" in sys.argv:
        scarica()
    X, y, giri, file = carica()
    print(f"{len(set(file))} registrazioni, {len(y)} finestre, da {giri.min():.0f} a {giri.max():.0f} giri/s; "
          + ", ".join(f"{c} {len(set(file[y == i]))} registrazioni" for i, c in enumerate(CLASSI)))

    # 1. il modello della scheda: addestrato su 28-32 giri/s, provato sul resto
    vicino = (giri >= 28) & (giri <= 32)
    m = nuovo_modello().fit(X[vicino], y[vicino])
    scala = m.named_steps["standardscaler"]
    fuori = np.abs((X[~vicino] - scala.mean_) / scala.scale_).max(axis=1) > LIMITE
    previsto = np.where(fuori, len(CLASSI), m.predict(X[~vicino]))
    print(f"\n1. modello di oggi su {np.sum(~vicino)} finestre ad altre velocità: "
          f"{np.mean(fuori):.0%} 'sconosciuta', "
          f"tra le altre giuste {np.mean(previsto[~fuori] == y[~vicino][~fuori]):.0%}")
    stampa_confusione(y[~vicino], previsto, CLASSI + ["sconosciuta"])

    # 2. tutte le velocità, a fasce di 5 giri/s tenute da parte una alla volta
    fasce = (giri // 5).astype(int)
    previsto = np.empty_like(y)
    for addestra, prova in GroupKFold(n_splits=len(set(fasce))).split(X, y, fasce):
        previsto[prova] = nuovo_modello().fit(X[addestra], y[addestra]).predict(X[prova])
    print(f"\n2. addestrato su tutte le velocità, provato su fasce di 5 giri/s mai viste: "
          f"accuratezza bilanciata {balanced_accuracy_score(y, previsto):.2f}")
    stampa_confusione(y, previsto, CLASSI)
    for f in sorted(set(fasce)):
        s = fasce == f
        print(f"  {f * 5:>2}-{f * 5 + 5:<2} giri/s: {balanced_accuracy_score(y[s], previsto[s]):.2f}")


if __name__ == "__main__":
    main()
