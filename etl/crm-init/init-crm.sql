CREATE TABLE clients (
                         id           SERIAL PRIMARY KEY,
                         username     TEXT      NOT NULL UNIQUE,
                         full_name    TEXT      NOT NULL,
                         city         TEXT,
                         model        TEXT,
                         purchased_at DATE,
                         updated_at   TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_clients_updated_at ON clients (updated_at);

INSERT INTO clients (username, full_name, city, model, purchased_at) VALUES
                                                                         ('prothetic1', 'Prothetic One',   'Москва',          'BP-Arm 3',  '2026-02-11'),
                                                                         ('prothetic2', 'Prothetic Two',   'Санкт-Петербург', 'BP-Arm 3S', '2026-04-02'),
                                                                         ('prothetic3', 'Prothetic Three', 'Казань',          'BP-Hand 2', '2026-06-20');