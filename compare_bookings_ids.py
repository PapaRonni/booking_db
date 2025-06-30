import requests
import psycopg2
from psycopg2 import OperationalError
from datetime import datetime
from env_settings import login, api_key, db_host, db_port, db_name, db_user, db_password

LOGIN = login
API_KEY = api_key

url_get_bookings = "https://litepms.ru/api/getBookings"
url_get_booking = "https://litepms.ru/api/getBooking"
params = {
    "login": LOGIN,
    "hash": API_KEY,
    "start": "2025-05-01",   # укажи нужный диапазон дат
    "finish": datetime.now().strftime("%Y-%m-%d")
}

# Получаем id всех броней за период
all_ids = []
page = 1
while True:
    params["page"] = str(page)
    response = requests.get(url_get_bookings, params=params)
    if response.status_code != 200:
        print("Ошибка HTTP:", response.status_code, response.text)
        break
    data = response.json()
    if data.get("status") != "success":
        print("Ошибка в ответе API:", data)
        break
    page_ids = data.get("data", [])
    if not page_ids:
        break
    all_ids.extend([b['id'] for b in page_ids if 'id' in b])
    if page >= data.get("pages", 1):
        break
    page += 1

print(f"Получено id из getBookings: {len(all_ids)}")

# Получаем booking_id для каждого id через getBooking
api_booking_ids = set()
for booking_id in all_ids:
    detail_params = {
        "login": LOGIN,
        "hash": API_KEY,
        "id": booking_id
    }
    resp = requests.get(url_get_booking, params=detail_params)
    if resp.status_code == 200:
        detail_data = resp.json()
        if detail_data.get("status") == "success":
            data = detail_data.get("data", {})
            if "booking_id" in data:
                api_booking_ids.add(int(data["booking_id"]))
        else:
            print(f"Ошибка в ответе getBooking для id={booking_id}: {detail_data}")
    else:
        print(f"Ошибка HTTP при getBooking для id={booking_id}: {resp.status_code}")

print(f"Получено booking_id из API: {len(api_booking_ids)}")

# Получаем booking_id из таблицы bookings
try:
    conn = psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port
    )
    cur = conn.cursor()
    cur.execute("SELECT booking_id FROM bookings")
    db_booking_ids = set(row[0] for row in cur.fetchall())
    cur.close()
    conn.close()
except OperationalError as e:
    print(f"Ошибка подключения к базе данных: {e}")
    db_booking_ids = set()

print(f"Получено booking_id из базы: {len(db_booking_ids)}")

# Сравнение
missing_in_db = api_booking_ids - db_booking_ids
missing_in_api = db_booking_ids - api_booking_ids

if missing_in_db:
    print("ВНИМАНИЕ! Следующие booking_id есть в API, но отсутствуют в таблице bookings:")
    print(sorted(missing_in_db))
else:
    print("Все booking_id из API присутствуют в таблице.")

if missing_in_api:
    print("ВНИМАНИЕ! Следующие booking_id есть в таблице bookings, но отсутствуют в API:")
    print(sorted(missing_in_api))
else:
    print("Все booking_id из таблицы присутствуют в API.")