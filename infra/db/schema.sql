-- Una riga per ogni messaggio dell'ESP32 (circa una al secondo).
-- ts è l'ora di arrivo: l'ESP32 non ha un orologio.
CREATE TABLE misure (
    ts          timestamptz NOT NULL DEFAULT now(),
    dispositivo text        NOT NULL,
    rms_g       real        NOT NULL,
    picco_hz    real,                  -- NULL: nessun picco sopra soglia
    picco_g     real,
    persi       integer     NOT NULL,
    saltati     integer     NOT NULL,
    classe      text,                  -- dal classificatore sulla scheda; NULL nei messaggi più vecchi
    confidenza  real
);

-- Hypertable: TimescaleDB divide la tabella in blocchi per tempo,
-- così le query "ultima ora" restano veloci anche con milioni di righe.
SELECT create_hypertable('misure', by_range('ts'));

-- Utente per l'agente: può solo leggere, e ogni query si ferma dopo 5 secondi.
-- Anche se il modello linguistico sbagliasse una query, non potrebbe cambiare né bloccare nulla.
CREATE ROLE agente LOGIN PASSWORD 'agente';
GRANT SELECT ON misure TO agente;
ALTER ROLE agente SET statement_timeout = '5s';
ALTER ROLE agente SET default_transaction_read_only = on;
