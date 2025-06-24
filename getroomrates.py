import requests
import psycopg2
from psycopg2 import OperationalError
import json
from env_settings import login, api_key, db_host, db_port, db_name, db_user, db_password

LOGIN = login
API_KEY = api_key

# Получаем список номеров
rooms_url = "https://litepms.ru/api/getRooms"
rooms_params = {
    "login": LOGIN,
    "hash": API_KEY
}

response = requests.get(rooms_url, params=rooms_params)
rooms_data = response.json()

print("Ответ сервера:", rooms_data)
if rooms_data.get("status") != "success":
    print("Ошибка получения списка номеров")
    exit(1)

rooms = rooms_data.get("data", [])
print(f"Получено номеров: {len(rooms)}")

# Для каждого номера получаем тарифы
rates_url = "https://litepms.ru/api/getRoomRates"
all_rates = []

for room in rooms:
    room_id = room.get("id")
    if not room_id:
        continue
    params = {
        "login": LOGIN,
        "hash": API_KEY,
        "room_id": room_id
    }
    rate_resp = requests.get(rates_url, params=params)
    rate_data = rate_resp.json()
    if rate_data.get("status") != "success":
        print(f"Ошибка получения тарифов для номера {room_id}: {rate_data}")
        continue
    rates = rate_data.get("data", [])
    print(f"room_id={room_id}, тарифов: {len(rates)}")
    all_rates.append({
        "room_id": room_id,
        "rates": rates
    })

# Параметры подключения к вашей базе данных
try:
    conn = psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port
    )
    cur = conn.cursor()
except OperationalError as e:
    print(f"Ошибка подключения к базе данных: {e}")
    conn = None
    cur = None

# Создание таблицы, если не существует
if conn and cur:
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS room_rates (
                room_id      INT     NOT NULL,
                rate_id      INT     NOT NULL,
                title        TEXT,
                mon          NUMERIC,
                tue          NUMERIC,
                wed          NUMERIC,
                thu          NUMERIC,
                fri          NUMERIC,
                sat          NUMERIC,
                sun          NUMERIC,
                add_mon      NUMERIC,
                add_tue      NUMERIC,
                add_wed      NUMERIC,
                add_thu      NUMERIC,
                add_fri      NUMERIC,
                add_sat      NUMERIC,
                add_sun      NUMERIC,
                PRIMARY KEY (room_id, rate_id)
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"Ошибка при создании таблицы: {e}")

# Вставка/обновление тарифов
if conn and cur:
    for room in all_rates:
        room_id = int(room["room_id"])
        for rate in room["rates"]:
            try:
                cur.execute('''
                    INSERT INTO room_rates (
                        room_id, rate_id, title, mon, tue, wed, thu, fri, sat, sun,
                        add_mon, add_tue, add_wed, add_thu, add_fri, add_sat, add_sun
                    ) VALUES (
                        %(room_id)s, %(rate_id)s, %(title)s, %(mon)s, %(tue)s, %(wed)s, %(thu)s, %(fri)s, %(sat)s, %(sun)s,
                        %(add_mon)s, %(add_tue)s, %(add_wed)s, %(add_thu)s, %(add_fri)s, %(add_sat)s, %(add_sun)s
                    )
                    ON CONFLICT (room_id, rate_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        mon = EXCLUDED.mon,
                        tue = EXCLUDED.tue,
                        wed = EXCLUDED.wed,
                        thu = EXCLUDED.thu,
                        fri = EXCLUDED.fri,
                        sat = EXCLUDED.sat,
                        sun = EXCLUDED.sun,
                        add_mon = EXCLUDED.add_mon,
                        add_tue = EXCLUDED.add_tue,
                        add_wed = EXCLUDED.add_wed,
                        add_thu = EXCLUDED.add_thu,
                        add_fri = EXCLUDED.add_fri,
                        add_sat = EXCLUDED.add_sat,
                        add_sun = EXCLUDED.add_sun
                ''', {
                    "room_id": room_id,
                    "rate_id": int(rate.get("id", 0)),
                    "title": rate.get("title", ""),
                    "mon": rate.get("mon"),
                    "tue": rate.get("tue"),
                    "wed": rate.get("wed"),
                    "thu": rate.get("thu"),
                    "fri": rate.get("fri"),
                    "sat": rate.get("sat"),
                    "sun": rate.get("sun"),
                    "add_mon": rate.get("add_mon"),
                    "add_tue": rate.get("add_tue"),
                    "add_wed": rate.get("add_wed"),
                    "add_thu": rate.get("add_thu"),
                    "add_fri": rate.get("add_fri"),
                    "add_sat": rate.get("add_sat"),
                    "add_sun": rate.get("add_sun")
                })
            except Exception as e:
                print(f"Ошибка при вставке/обновлении тарифа room_id={room_id}, rate_id={rate.get('id')}: {e}")
    try:
        conn.commit()
    except Exception as e:
        print(f"Ошибка при коммите: {e}")
    finally:
        cur.close()
        conn.close()
else:
    print("Нет подключения к базе данных, данные не записаны.")

# Выводим результат для анализа структуры
print(json.dumps(all_rates, ensure_ascii=False, indent=2)) 