-- Una riga per ogni messaggio dell'ESP32 (circa una al secondo).
-- ts è l'ora di arrivo: l'ESP32 non ha un orologio.
CREATE TABLE misure (
    ts          timestamptz NOT NULL DEFAULT now(),
    dispositivo text        NOT NULL,
    rms_g       real        NOT NULL,
    picco_hz    real,                  -- NULL: nessun picco sopra soglia
    picco_g     real,
    persi       integer     NOT NULL,
    saltati     integer     NOT NULL
);

-- Hypertable: TimescaleDB divide la tabella in blocchi per tempo,
-- così le query "ultima ora" restano veloci anche con milioni di righe.
SELECT create_hypertable('misure', by_range('ts'));
