CREATE TABLE rates_conditions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    room_id INTEGER NOT NULL,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    monday DECIMAL(10,2),
    tuesday DECIMAL(10,2),
    wednesday DECIMAL(10,2),
    thursday DECIMAL(10,2),
    friday DECIMAL(10,2),
    saturday DECIMAL(10,2),
    sunday DECIMAL(10,2),
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);