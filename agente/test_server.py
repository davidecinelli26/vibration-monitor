"""I test usano una tabella temporanea `misure`: PostgreSQL la cerca prima di quella vera,
quindi i dati di prova non toccano il database e spariscono a fine test."""
import os

import psycopg
import pytest

import server

URL_TEST = os.getenv("DB_URL_TEST", "postgresql://vibrazioni:vibrazioni@127.0.0.1:5432/vibrazioni")


@pytest.fixture
def db():
    try:
        conn = psycopg.connect(URL_TEST, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("database non raggiungibile: avvia infra/ con docker compose")
    conn.execute("""
        CREATE TEMP TABLE misure (
            ts timestamptz NOT NULL, dispositivo text NOT NULL, rms_g real NOT NULL,
            picco_hz real, picco_g real, persi integer NOT NULL, saltati integer NOT NULL,
            classe text, confidenza real)
    """)
    server.conn = conn
    yield conn
    server.conn = None
    conn.close()


def inserisci(conn, dispositivo, minuti_fa, rms, hz=29.3, classe="normale", persi=0, saltati=0):
    """Una misura al minuto, per ciascuno dei minuti indicati."""
    for m in minuti_fa:
        conn.execute(
            "INSERT INTO misure VALUES (now() - %s * interval '1 minute', %s, %s, %s, 0.1, %s, %s, %s, 0.9)",
            (m, dispositivo, rms, hz, persi, saltati, classe))


def test_elenca_dispositivi(db):
    inserisci(db, "a", [1, 2, 3], 0.1)
    inserisci(db, "b", [1], 0.2)
    assert [(d["dispositivo"], d["misure"]) for d in server.elenca_dispositivi()] == [("a", 3), ("b", 1)]


def test_elenca_dispositivi_ultima_classe(db):
    inserisci(db, "a", [5, 4], 0.1, classe="normale")
    inserisci(db, "a", [1], 0.3, classe="squilibrio")
    assert server.elenca_dispositivi()[0]["classe"] == "squilibrio"


def test_stato_classe_piu_frequente(db):
    inserisci(db, "a", [1.1, 1.2], 0.2, classe="squilibrio")
    inserisci(db, "a", [1.3], 0.2, classe="normale")
    assert [r["classe"] for r in server.stato("a", minuti=600)] == ["squilibrio"]   # intervalli da 50 minuti: tutte nello stesso


def test_stato_un_valore_al_minuto(db):
    inserisci(db, "a", [1.2, 1.5, 30], 0.2)      # la misura di 30 minuti fa è fuori dalla finestra
    risultato = server.stato("a", minuti=10)
    assert sum(r["misure"] for r in risultato) == 2
    assert all(r["rms_g"] == pytest.approx(0.2) for r in risultato)
    assert isinstance(risultato[0]["da"], str)    # data già pronta per il JSON


def test_anomalie_trova_chi_peggiora(db):
    inserisci(db, "sana", range(1, 60), 0.16)                    # sempre uguale
    inserisci(db, "guasta", range(6, 60), 0.16)                  # prima: 0,16
    inserisci(db, "guasta", range(1, 5), 0.52, hz=29.3)          # ora: 0,52
    risultato = server.trova_anomalie(minuti=5, soglia=1.5)
    assert [r["dispositivo"] for r in risultato] == ["guasta"]
    r = risultato[0]
    assert r["rms_prima"] == pytest.approx(0.16, abs=1e-3)
    assert r["rms_ora"] == pytest.approx(0.52, abs=1e-3)
    assert r["rapporto"] == pytest.approx(3.25, abs=0.01)
    assert r["picco_hz_ora"] == pytest.approx(29.3, abs=0.01)


def test_anomalie_ordinate_dal_rapporto_piu_alto(db):
    for nome, rms_ora in [("x2", 0.2), ("x5", 0.5), ("x3", 0.3)]:
        inserisci(db, nome, range(6, 60), 0.1)
        inserisci(db, nome, range(1, 5), rms_ora)
    assert [r["dispositivo"] for r in server.trova_anomalie(5, 1.5)] == ["x5", "x3", "x2"]


def test_anomalie_ignora_macchine_senza_storia(db):
    inserisci(db, "nuova", range(1, 5), 0.9)       # nessuna misura "prima": niente confronto
    assert server.trova_anomalie(5, 1.5) == []


def test_anomalie_ignora_misure_troppo_vecchie(db):
    inserisci(db, "a", range(70, 100), 0.01)       # più di un'ora prima del periodo: non conta
    inserisci(db, "a", range(6, 60), 0.2)
    inserisci(db, "a", range(1, 5), 0.25)          # 0,25 / 0,2 = 1,25: sotto soglia
    assert server.trova_anomalie(5, 1.5) == []


def test_sensori_conta_quanto_crescono_i_contatori(db):
    inserisci(db, "sano", range(1, 60), 0.1, persi=116)             # fermo a 116: non perde più nulla
    inserisci(db, "guasto", range(6, 60), 0.1, persi=3)
    inserisci(db, "guasto", range(1, 5), 0.1, persi=40, saltati=2)
    risultato = server.sensori()
    assert [(r["dispositivo"], r["persi"], r["saltati"]) for r in risultato] == [("guasto", 37, 2)]
    assert isinstance(risultato[0]["da"], str)


def test_sensori_ignora_perdite_vecchie(db):
    inserisci(db, "a", range(70, 100), 0.1, persi=0)
    inserisci(db, "a", range(1, 60), 0.1, persi=50)                  # la perdita è di più di un'ora fa
    assert server.sensori() == []


def test_strumenti_registrati():
    import asyncio
    nomi = {t.name for t in asyncio.run(server.server.list_tools())}
    assert nomi == {"elenca_dispositivi", "stato", "anomalie", "sensori"}
