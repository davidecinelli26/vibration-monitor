from sorveglia import da_avvisare, messaggio_di_riserva

ORA = 1_000_000.0
PAUSA = 3600


def test_mai_avvisata():
    assert da_avvisare(["anomalia:motore-1"], {}, ORA, PAUSA) == ["anomalia:motore-1"]


def test_avvisata_da_poco_non_si_ripete():
    assert da_avvisare(["anomalia:motore-1"], {"anomalia:motore-1": ORA - 600}, ORA, PAUSA) == []


def test_dopo_la_pausa_si_avvisa_di_nuovo():
    assert da_avvisare(["anomalia:motore-1"], {"anomalia:motore-1": ORA - 2 * PAUSA}, ORA, PAUSA) == ["anomalia:motore-1"]


def test_conta_ogni_chiave_per_conto_suo():
    # stessa macchina, problema diverso: è un avviso nuovo
    ultimi = {"anomalia:motore-1": ORA - 600}
    chiavi = ["anomalia:motore-1", "sensore:motore-1", "anomalia:motore-2"]
    assert da_avvisare(chiavi, ultimi, ORA, PAUSA) == ["sensore:motore-1", "anomalia:motore-2"]


def test_niente_da_segnalare():
    assert da_avvisare([], {"anomalia:motore-1": ORA - 600}, ORA, PAUSA) == []


def test_messaggio_di_riserva_ha_i_numeri():
    testo = messaggio_di_riserva({"sensore:motore-2": {"dispositivo": "motore-2", "persi": 37}})
    assert "sensore:motore-2" in testo and "37" in testo
