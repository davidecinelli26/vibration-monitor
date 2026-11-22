from ingestor import riga_da_messaggio


def test_messaggio_completo():
    testo = (b'{"dispositivo":"esp32-1","rms_g":0.2119,"picco_hz":49.8,"picco_g":0.2803,"persi":0,"saltati":3,'
             b'"classe":"squilibrio","confidenza":0.88}')
    assert riga_da_messaggio(testo) == ("esp32-1", 0.2119, 49.8, 0.2803, 0, 3, "squilibrio", 0.88)


def test_senza_classe():
    testo = b'{"dispositivo":"esp32-1","rms_g":0.2119,"picco_hz":49.8,"picco_g":0.2803,"persi":0,"saltati":3}'
    assert riga_da_messaggio(testo) == ("esp32-1", 0.2119, 49.8, 0.2803, 0, 3, None, None)


def test_picco_null_diventa_none():
    testo = b'{"dispositivo":"esp32-1","rms_g":0.001,"picco_hz":null,"picco_g":null,"persi":0,"saltati":0}'
    assert riga_da_messaggio(testo) == ("esp32-1", 0.001, None, None, 0, 0, None, None)


def test_json_rotto():
    assert riga_da_messaggio(b'{"dispositivo":"esp32-1",') is None


def test_manca_rms():
    assert riga_da_messaggio(b'{"dispositivo":"esp32-1","persi":0,"saltati":0}') is None


def test_non_un_oggetto():
    assert riga_da_messaggio(b'[1, 2, 3]') is None
