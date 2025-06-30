import requests
import psycopg2
from psycopg2 import OperationalError
from datetime import datetime
from env_settings import login, api_key, db_host, db_port, db_name, db_user, db_password

LOGIN = login
API_KEY = api_key

url = "https://litepms.ru/api/getBookings"
params = {
    "login": LOGIN,
    "hash": API_KEY,
    "start": "2025-06-10",   # укажи нужный диапазон дат (last_update)
    "finish": datetime.now().strftime("%Y-%m-%d")
}

def to_bool(val):
    return str(val) == '1'

def to_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def to_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def to_timestamp(val):
    if not val or val in ('', None):
        return None
    return val  # psycopg2 сам преобразует строку

def get_field(d, key, default=None):
    return d.get(key, default)

# Получаем id всех броней за период
bookings_ids = []
page = 1
while True:
    params["page"] = str(page)
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print("Ошибка HTTP:", response.status_code, response.text)
        break
    data = response.json()
    if data.get("status") != "success":
        print("Ошибка в ответе API:", data)
        break
    page_ids = data.get("data", [])
    # print(f"DEBUG: page_ids = {page_ids}")
    if not page_ids:
        break
    bookings_ids.extend(page_ids)
    if page >= data.get("pages", 1):
        break
    page += 1

id_list = [int(b['id']) for b in bookings_ids if 'id' in b]

# Получаем полные данные по каждой брони
all_bookings = []
for booking_id in id_list:
    detail_params = {
        "login": LOGIN,
        "hash": API_KEY,
        "id": booking_id
    }
    detail_url = "https://litepms.ru/api/getBooking"
    resp = requests.get(detail_url, params=detail_params)
    if resp.status_code == 200:
        detail_data = resp.json()
        if detail_data.get("status") == "success":
            all_bookings.append(detail_data.get("data", {}))
        else:
            print(f"Ошибка в ответе getBooking для id={booking_id}: {detail_data}")
    else:
        print(f"Ошибка HTTP при getBooking для id={booking_id}: {resp.status_code}")

print(f"Загружено полных броней: {len(all_bookings)}")

# Запись в базу
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

if all_bookings and conn and cur:
    for b in all_bookings:
        try:
            client_id = to_int(get_field(b, "client_id"))
            if client_id == 0:
                print(f"Пропущена бронь {b.get('id')} из-за client_id=0")
                continue
            cur.execute("SELECT 1 FROM clients WHERE id = %s", (client_id,))
            if not cur.fetchone():
                print(f"Пропущена бронь {b.get('id')}: client_id {client_id} отсутствует в clients")
                continue
            cur.execute("""
                INSERT INTO bookings (
                    id, booking_id, author_id, author_name, date, last_update, stayprice, stayprice_type,
                    is_bed, bed_id, client_id, client_name, client_surname, client_middlename, client_phone,
                    client_email, client_booking_comment, comment, date_in, date_out, early_time_in, late_time_out,
                    person, person_add, price, payed, room_id, room_name, cat_id, status_id, status_name,
                    service_id, service_title, service_number
                ) VALUES (
                    %(id)s, %(booking_id)s, %(author_id)s, %(author_name)s, %(date)s, %(last_update)s, %(stayprice)s, %(stayprice_type)s,
                    %(is_bed)s, %(bed_id)s, %(client_id)s, %(client_name)s, %(client_surname)s, %(client_middlename)s, %(client_phone)s,
                    %(client_email)s, %(client_booking_comment)s, %(comment)s, %(date_in)s, %(date_out)s, %(early_time_in)s, %(late_time_out)s,
                    %(person)s, %(person_add)s, %(price)s, %(payed)s, %(room_id)s, %(room_name)s, %(cat_id)s, %(status_id)s, %(status_name)s,
                    %(service_id)s, %(service_title)s, %(service_number)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    booking_id = EXCLUDED.booking_id,
                    author_id = EXCLUDED.author_id,
                    author_name = EXCLUDED.author_name,
                    date = EXCLUDED.date,
                    last_update = EXCLUDED.last_update,
                    stayprice = EXCLUDED.stayprice,
                    stayprice_type = EXCLUDED.stayprice_type,
                    is_bed = EXCLUDED.is_bed,
                    bed_id = EXCLUDED.bed_id,
                    client_id = EXCLUDED.client_id,
                    client_name = EXCLUDED.client_name,
                    client_surname = EXCLUDED.client_surname,
                    client_middlename = EXCLUDED.client_middlename,
                    client_phone = EXCLUDED.client_phone,
                    client_email = EXCLUDED.client_email,
                    client_booking_comment = EXCLUDED.client_booking_comment,
                    comment = EXCLUDED.comment,
                    date_in = EXCLUDED.date_in,
                    date_out = EXCLUDED.date_out,
                    early_time_in = EXCLUDED.early_time_in,
                    late_time_out = EXCLUDED.late_time_out,
                    person = EXCLUDED.person,
                    person_add = EXCLUDED.person_add,
                    price = EXCLUDED.price,
                    payed = EXCLUDED.payed,
                    room_id = EXCLUDED.room_id,
                    room_name = EXCLUDED.room_name,
                    cat_id = EXCLUDED.cat_id,
                    status_id = EXCLUDED.status_id,
                    status_name = EXCLUDED.status_name,
                    service_id = EXCLUDED.service_id,
                    service_title = EXCLUDED.service_title,
                    service_number = EXCLUDED.service_number
            """, {
                "id": to_int(get_field(b, "id")),
                "booking_id": to_int(get_field(b, "booking_id")),
                "author_id": to_int(get_field(b, "author_id")),
                "author_name": get_field(b, "author_name"),
                "date": to_timestamp(get_field(b, "date")),
                "last_update": to_timestamp(get_field(b, "last_update")),
                "stayprice": to_float(get_field(b, "stayprice")),
                "stayprice_type": to_int(get_field(b, "stayprice_type")),
                "is_bed": to_bool(get_field(b, "is_bed")),
                "bed_id": to_int(get_field(b, "bed_id")),
                "client_id": client_id,
                "client_name": get_field(b, "client_name"),
                "client_surname": get_field(b, "client_surname"),
                "client_middlename": get_field(b, "client_middlename"),
                "client_phone": get_field(b, "client_phone"),
                "client_email": get_field(b, "client_email"),
                "client_booking_comment": get_field(b, "client_booking_comment"),
                "comment": get_field(b, "comment"),
                "date_in": to_timestamp(get_field(b, "date_in")),
                "date_out": to_timestamp(get_field(b, "date_out")),
                "early_time_in": to_bool(get_field(b, "early_time_in")),
                "late_time_out": to_bool(get_field(b, "late_time_out")),
                "person": to_int(get_field(b, "person")),
                "person_add": to_int(get_field(b, "person_add")),
                "price": to_float(get_field(b, "price")),
                "payed": to_float(get_field(b, "payed")),
                "room_id": to_int(get_field(b, "room_id")),
                "room_name": get_field(b, "room_name"),
                "cat_id": to_int(get_field(b, "cat_id")),
                "status_id": to_int(get_field(b, "status_id")),
                "status_name": get_field(b, "status_name"),
                "service_id": to_int(get_field(b, "service_id")),
                "service_title": get_field(b, "service_title"),
                "service_number": get_field(b, "service_number"),
            })
            print(f"Добавлена/обновлена бронь {b.get('id')}")
            conn.commit()
        except Exception as e:
            print(f"Ошибка при вставке брони {b.get('id')}: {e}")
            if conn:
                conn.rollback()