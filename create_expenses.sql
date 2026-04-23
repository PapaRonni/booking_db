CREATE TABLE expenses (
    id              SERIAL PRIMARY KEY,           -- уникальный идентификатор записи
    date            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, -- дата расхода
    amount          NUMERIC(12,2) NOT NULL,       -- сумма расхода
    purpose         TEXT NOT NULL,                -- назначение расхода
    expense_group   TEXT NOT NULL,                -- группа расходов
    comment         TEXT                          -- комментарий к расходу
);
