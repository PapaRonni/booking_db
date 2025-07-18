CREATE TABLE bookings (
    id            BIGINT PRIMARY KEY,         -- id бронирования (уникальный)
    booking_id    BIGINT,                     -- номер брони (видимый пользователю)
    author_id     BIGINT,
    author_name   TEXT,
    date          TIMESTAMP,
    last_update   TIMESTAMP,
    stayprice     NUMERIC(12,2),
    stayprice_type SMALLINT,
    is_bed        BOOLEAN,
    bed_id        BIGINT,
    client_id     BIGINT REFERENCES clients(id), -- внешний ключ на clients
    client_name   TEXT,
    client_surname TEXT,
    client_middlename TEXT,
    client_phone  TEXT,
    client_email  TEXT,
    client_booking_comment TEXT,
    comment       TEXT,
    date_in       TIMESTAMP,
    date_out      TIMESTAMP,
    early_time_in BOOLEAN,
    late_time_out BOOLEAN,
    person        SMALLINT,
    person_add    SMALLINT,
    price         NUMERIC(12,2),
    payed         NUMERIC(12,2),
    room_id       BIGINT,
    room_name     TEXT,
    cat_id        BIGINT,
    status_id     SMALLINT,
    status_name   TEXT,
    service_id    BIGINT,
    service_title TEXT,
    service_number TEXT
);