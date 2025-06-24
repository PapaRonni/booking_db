import requests
import psycopg2
from psycopg2 import OperationalError
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

# Создание таблицы rooms, если не существует
if conn and cur:
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                id INT PRIMARY KEY,
                cat_id INT,
                floor_id INT,
                corpus_id INT,
                number TEXT,
                name TEXT,
                widget_name TEXT,
                descr TEXT,
                descr2 TEXT,
                area NUMERIC,
                person INT,
                person_add INT,
                children INT,
                children_in_person INT,
                accom_opt TEXT,
                services TEXT,
                comfort TEXT,
                hourly INT,
                rate_id INT,
                price NUMERIC,
                price_for_bed NUMERIC,
                person_add_price NUMERIC,
                children_price NUMERIC,
                price_per_person NUMERIC,
                booking_mode INT,
                clean_status INT,
                sort INT,
                sort_bm INT,
                active INT,
                active_bm INT,
                active_cm INT,
                pay_method TEXT,
                color TEXT
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"Ошибка при создании таблицы rooms: {e}")

# Вставка/обновление информации о номерах
if conn and cur:
    for room in rooms:
        try:
            cur.execute('''
                INSERT INTO rooms (
                    id, cat_id, floor_id, corpus_id, number, name, widget_name, descr, descr2, area, person, person_add, children, children_in_person, accom_opt, services, comfort, hourly, rate_id, price, price_for_bed, person_add_price, children_price, price_per_person, booking_mode, clean_status, sort, sort_bm, active, active_bm, active_cm, pay_method, color
                ) VALUES (
                    %(id)s, %(cat_id)s, %(floor_id)s, %(corpus_id)s, %(number)s, %(name)s, %(widget_name)s, %(descr)s, %(descr2)s, %(area)s, %(person)s, %(person_add)s, %(children)s, %(children_in_person)s, %(accom_opt)s, %(services)s, %(comfort)s, %(hourly)s, %(rate_id)s, %(price)s, %(price_for_bed)s, %(person_add_price)s, %(children_price)s, %(price_per_person)s, %(booking_mode)s, %(clean_status)s, %(sort)s, %(sort_bm)s, %(active)s, %(active_bm)s, %(active_cm)s, %(pay_method)s, %(color)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    cat_id = EXCLUDED.cat_id,
                    floor_id = EXCLUDED.floor_id,
                    corpus_id = EXCLUDED.corpus_id,
                    number = EXCLUDED.number,
                    name = EXCLUDED.name,
                    widget_name = EXCLUDED.widget_name,
                    descr = EXCLUDED.descr,
                    descr2 = EXCLUDED.descr2,
                    area = EXCLUDED.area,
                    person = EXCLUDED.person,
                    person_add = EXCLUDED.person_add,
                    children = EXCLUDED.children,
                    children_in_person = EXCLUDED.children_in_person,
                    accom_opt = EXCLUDED.accom_opt,
                    services = EXCLUDED.services,
                    comfort = EXCLUDED.comfort,
                    hourly = EXCLUDED.hourly,
                    rate_id = EXCLUDED.rate_id,
                    price = EXCLUDED.price,
                    price_for_bed = EXCLUDED.price_for_bed,
                    person_add_price = EXCLUDED.person_add_price,
                    children_price = EXCLUDED.children_price,
                    price_per_person = EXCLUDED.price_per_person,
                    booking_mode = EXCLUDED.booking_mode,
                    clean_status = EXCLUDED.clean_status,
                    sort = EXCLUDED.sort,
                    sort_bm = EXCLUDED.sort_bm,
                    active = EXCLUDED.active,
                    active_bm = EXCLUDED.active_bm,
                    active_cm = EXCLUDED.active_cm,
                    pay_method = EXCLUDED.pay_method,
                    color = EXCLUDED.color
            ''', {
                "id": int(room.get("id", 0)),
                "cat_id": int(room.get("cat_id", 0)),
                "floor_id": int(room.get("floor_id", 0)),
                "corpus_id": int(room.get("corpus_id", 0)),
                "number": room.get("number", ""),
                "name": room.get("name", ""),
                "widget_name": room.get("widget_name", ""),
                "descr": room.get("descr", ""),
                "descr2": room.get("descr2", ""),
                "area": room.get("area"),
                "person": int(room.get("person", 0)),
                "person_add": int(room.get("person_add", 0)),
                "children": int(room.get("children", 0)),
                "children_in_person": int(room.get("children_in_person", 0)),
                "accom_opt": room.get("accom_opt", ""),
                "services": room.get("services", ""),
                "comfort": room.get("comfort", ""),
                "hourly": int(room.get("hourly", 0)),
                "rate_id": int(room.get("rate_id", 0)),
                "price": room.get("price"),
                "price_for_bed": room.get("price_for_bed"),
                "person_add_price": room.get("person_add_price"),
                "children_price": room.get("children_price"),
                "price_per_person": room.get("price_per_person"),
                "booking_mode": int(room.get("booking_mode", 0)),
                "clean_status": int(room.get("clean_status", 0)),
                "sort": int(room.get("sort", 0)),
                "sort_bm": int(room.get("sort_bm", 0)),
                "active": int(room.get("active", 0)),
                "active_bm": int(room.get("active_bm", 0)),
                "active_cm": int(room.get("active_cm", 0)),
                "pay_method": room.get("pay_method", ""),
                "color": room.get("color", "")
            })
        except Exception as e:
            print(f"Ошибка при вставке/обновлении номера id={room.get('id')}: {e}")
    try:
        conn.commit()
    except Exception as e:
        print(f"Ошибка при коммите (rooms): {e}")
else:
    print("Нет подключения к базе данных, данные не записаны.") 