"""Scarica in dati/ le registrazioni usate da replay.py.

CWRU: 4 file .mat, circa 13 MB.
MAFAULDA: legge 4 archivi (5,8 GB) mentre arrivano e salva solo le registrazioni
tra 28 e 32 giri al secondo (72 file, circa 1,2 GB). Ci vogliono parecchi minuti.

Avvio:  uv run python scarica_dati.py
"""
import tarfile
import urllib.request
from pathlib import Path

DATI = Path(__file__).parent / "dati"
CWRU = "https://engineering.case.edu/sites/default/files/{}.mat"
MAFAULDA = "https://www02.smt.ufrj.br/~offshore/mfs/database/mafaulda/{}.tgz"


def cwru() -> None:
    for n in (97, 105, 118, 130):
        dest = DATI / f"{n}.mat"
        if not dest.exists():
            print(f"scarico {dest.name}")
            urllib.request.urlretrieve(CWRU.format(n), dest)


def mafaulda(archivio: str) -> None:
    dest = DATI / "mafaulda"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"leggo {archivio}.tgz")
    with urllib.request.urlopen(MAFAULDA.format(archivio)) as r, tarfile.open(fileobj=r, mode="r|gz") as tar:
        for m in tar:
            if not m.isfile() or not m.name.endswith(".csv"):
                continue
            try:
                hz = float(Path(m.name).stem)       # il nome del file è la velocità di rotazione
            except ValueError:
                continue
            if 28 <= hz <= 32:
                # nome piatto, senza cartelle: un archivio non può scrivere fuori da dati/
                nome = m.name.replace("/", "__")
                with tar.extractfile(m) as src:
                    (dest / nome).write_bytes(src.read())


if __name__ == "__main__":
    DATI.mkdir(exist_ok=True)
    cwru()
    for a in ("normal", "imbalance", "horizontal-misalignment", "vertical-misalignment"):
        mafaulda(a)
