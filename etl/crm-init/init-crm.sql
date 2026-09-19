CREATE TABLE clients (
                         id               SERIAL PRIMARY KEY,
                         keycloak_user_id UUID      NOT NULL UNIQUE,
                         full_name        TEXT      NOT NULL,
                         city             TEXT,
                         model            TEXT,
                         purchased_at     DATE,
                         updated_at       TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_clients_updated_at ON clients (updated_at);

-- keycloak_user_id должен совпадать с sub пользователя в Keycloak.
INSERT INTO clients (keycloak_user_id, full_name, city, model, purchased_at) VALUES
                                                                                 ('11111111-1111-1111-1111-111111111111', 'Иванов Иван',     'Москва',          'BP-Arm 3',  '2026-02-11'),
                                                                                 ('22222222-2222-2222-2222-222222222222', 'Петрова Мария',   'Санкт-Петербург', 'BP-Arm 3S', '2026-04-02'),
                                                                                 ('33333333-3333-3333-3333-333333333333', 'Сидоров Алексей', 'Казань',          'BP-Hand 2', '2026-06-20');
