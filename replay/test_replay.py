import json

import numpy as np
import pytest

from replay import DATI, FS, N, analizza, carica, classifica, leggi_modello, messaggio

t = np.arange(N) / FS


def test_sinusoide_come_nel_firmware():
    # gli stessi numeri che stampava l'ESP32 in Wokwi
    rms, hz, g = analizza(1.0 + 0.3 * np.sin(2 * np.pi * 50 * t))
    assert rms == pytest.approx(0.2121, abs=1e-3)
    assert hz == pytest.approx(49.8, abs=0.05)
    assert g == pytest.approx(0.28, abs=0.01)


def test_frequenza_esatta_su_un_bin():
    # 125 Hz = bin 128 esatto: niente dispersione, ampiezza piena
    rms, hz, g = analizza(0.5 * np.sin(2 * np.pi * 125 * t))
    assert hz == 125.0
    assert g == pytest.approx(0.5, abs=1e-6)


def test_segnale_costante():
    rms, hz, g = analizza(np.full(N, 1.0))
    assert rms == pytest.approx(0.0, abs=1e-9)
    assert g == pytest.approx(0.0, abs=1e-9)


def test_restituisce_float_normali():
    # json.dumps non sa scrivere i tipi di numpy: servono float di Python
    assert all(type(v) is float for v in analizza(np.sin(2 * np.pi * 50 * t)))


def test_messaggio_sotto_soglia():
    d = json.loads(messaggio("prova", 0.001, 12.7, 0.001, "normale", 0.9))
    assert d["picco_hz"] is None and d["picco_g"] is None


@pytest.mark.skipif(not (DATI / "105.mat").exists(), reason="dati CWRU non scaricati")
def test_cwru_anello_interno_picco_stabile():
    # Nel file originale a 12 kHz il componente più forte sotto 500 Hz è a 455 Hz (0,021 g).
    # Dopo il passaggio a 1 kHz deve restare lì in ogni finestra: se il ricampionamento
    # rovinasse il segnale (aliasing, fattore sbagliato) il picco si sposterebbe.
    x = carica(DATI / "105.mat", 12000)
    assert len(x) == pytest.approx(121265 / 12, abs=1)
    picchi = [analizza(x[i:i + N])[1] for i in range(0, len(x) - N + 1, N)]
    assert all(abs(hz - 455) < 2 for hz in picchi)


def finestre(nome, fs):
    x = carica(DATI / nome, fs)
    return [analizza(x[i:i + N]) for i in range(0, len(x) - N + 1, N)]


@pytest.mark.skipif(not (DATI / "mafaulda").exists(), reason="dati MAFAULDA non scaricati")
def test_mafaulda_squilibrio_si_vede():
    # Lo squilibrio fa vibrare l'albero una volta per giro: picco a circa 29,5 Hz,
    # e RMS circa 3 volte quello del motore sano (misurato: 0,51 contro 0,16).
    sano = finestre("mafaulda/normal__29.4912.csv", 51200)
    squilibrio = finestre("mafaulda/imbalance__20g__29.4912.csv", 51200)
    assert all(abs(hz - 29.5) < 1 for _, hz, _ in squilibrio)
    rms = lambda f: sum(r for r, _, _ in f) / len(f)
    assert rms(squilibrio) > 2.5 * rms(sano)


def test_motore_1_peggiora_e_poi_resta_sull_ultima_fase():
    from replay import FASE_FINESTRE, SCENARIO_MOTORE_1, fase_motore_1
    assert fase_motore_1(0) == "mafaulda-normale"
    assert fase_motore_1(FASE_FINESTRE) == "mafaulda-squilibrio-6g"
    assert fase_motore_1(100 * FASE_FINESTRE) == SCENARIO_MOTORE_1[-1]


def test_modello_letto_dal_firmware():
    m = leggi_modello()
    assert m["NOMI_CLASSI"] == ["normale", "squilibrio", "disallineamento", "sconosciuta"]
    assert m["PESI"].shape == (3, 17) and len(m["MEDIA"]) == len(m["SCALA"]) == 17


@pytest.mark.skipif(not (DATI / "mafaulda").exists(), reason="dati MAFAULDA non scaricati")
@pytest.mark.parametrize("nome, attesa", [
    ("normal__29.4912.csv", "normale"),
    ("imbalance__20g__29.4912.csv", "squilibrio"),
    ("vertical-misalignment__1.90mm__29.9008.csv", "disallineamento"),
])
def test_classe_delle_registrazioni_mafaulda(nome, attesa):
    # file visti in addestramento: controlla che il replay calcoli come il Python dello studio
    m = leggi_modello()
    x = carica(DATI / "mafaulda" / nome, 51200)
    classi = [classifica(x[i:i + N], m)[0] for i in range(0, len(x) - N + 1, N)]
    assert classi.count(attesa) >= 0.9 * len(classi)


@pytest.mark.skipif(not (DATI / "105.mat").exists(), reason="dati CWRU non scaricati")
def test_cwru_e_sconosciuta():
    # un'altra macchina, un altro sensore: il modello non la conosce e deve dirlo
    m = leggi_modello()
    x = carica(DATI / "105.mat", 12000)
    assert {classifica(x[i:i + N], m)[0] for i in range(0, len(x) - N + 1, N)} == {"sconosciuta"}
