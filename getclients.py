import requests
import psycopg2
from psycopg2 import OperationalError
from env_settings import login, api_key, db_host, db_port, db_name, db_user, db_password

# Замените на свои значения
LOGIN = login
API_KEY = api_key

url = "https://litepms.ru/api/getClients"
params = {
    "login": LOGIN,
    "hash": API_KEY
}

def to_bool(val):
    return str(val) == '1'

def to_date(val):
    s = get_field(val, None) if isinstance(val, dict) else val
    if s in ('0000-00-00', '', None):
        return None
    try:
        return s[:10]  # 'YYYY-MM-DD'
    except Exception:
        return None

def to_timestamp(val):
    s = get_field(val, None) if isinstance(val, dict) else val
    if not s or s in ('', None):
        return None
    try:
        # psycopg2 сам преобразует строку 'YYYY-MM-DD HH:MM:SS' в TIMESTAMP
        return s
    except Exception:
        return None

def to_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def get_field(client, field, default=None):
    return client.get(field, default)

# --- Загрузка всех клиентов с постраничным обходом ---
clients = []
page = 1
while True:
    params["page"] = str(page)
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print("Ошибка HTTP:", response.status_code, response.text)
            break
        data = response.json()
        if data.get("status") != "success":
            print("Ошибка в ответе API:", data)
            break
        page_clients = data.get("data", [])
        if not page_clients:
            break
        clients.extend(page_clients)
        print(f"Загружено клиентов: {len(clients)} (страница {page})")
        if page >= data.get("pages", 1):
            break
        page += 1
    except Exception as e:
        print(f"Ошибка при запросе к API: {e}")
        break

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

if clients and conn and cur:
    for client in clients:
        try:
            print("Вставляем клиента:", client)
            cur.execute("""
                INSERT INTO clients (
                    id, user_id, group_id, date, name, middlename, surname, extradata, birthday, birthday_place,
                    phone, email, social, address, doc_title, doc_series, doc_code, doc_when, doc_valid, doc_where,
                    comment, anketa, bl, vip, adv, gender, foreigner, is_live, pref
                ) VALUES (
                    %(id)s, %(user_id)s, %(group_id)s, %(date)s, %(name)s, %(middlename)s, %(surname)s, %(extradata)s, %(birthday)s, %(birthday_place)s,
                    %(phone)s, %(email)s, %(social)s, %(address)s, %(doc_title)s, %(doc_series)s, %(doc_code)s, %(doc_when)s, %(doc_valid)s, %(doc_where)s,
                    %(comment)s, %(anketa)s, %(bl)s, %(vip)s, %(adv)s, %(gender)s, %(foreigner)s, %(is_live)s, %(pref)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    group_id = EXCLUDED.group_id,
                    date = EXCLUDED.date,
                    name = EXCLUDED.name,
                    middlename = EXCLUDED.middlename,
                    surname = EXCLUDED.surname,
                    extradata = EXCLUDED.extradata,
                    birthday = EXCLUDED.birthday,
                    birthday_place = EXCLUDED.birthday_place,
                    phone = EXCLUDED.phone,
                    email = EXCLUDED.email,
                    social = EXCLUDED.social,
                    address = EXCLUDED.address,
                    doc_title = EXCLUDED.doc_title,
                    doc_series = EXCLUDED.doc_series,
                    doc_code = EXCLUDED.doc_code,
                    doc_when = EXCLUDED.doc_when,
                    doc_valid = EXCLUDED.doc_valid,
                    doc_where = EXCLUDED.doc_where,
                    comment = EXCLUDED.comment,
                    anketa = EXCLUDED.anketa,
                    bl = EXCLUDED.bl,
                    vip = EXCLUDED.vip,
                    adv = EXCLUDED.adv,
                    gender = EXCLUDED.gender,
                    foreigner = EXCLUDED.foreigner,
                    is_live = EXCLUDED.is_live,
                    pref = EXCLUDED.pref
            """, {
                "id": to_int(get_field(client, "id")),
                "user_id": to_int(get_field(client, "user_id")),
                "group_id": to_int(get_field(client, "group_id")),
                "date": to_timestamp(get_field(client, "date")),
                "name": get_field(client, "name", ""),
                "middlename": get_field(client, "middlename", ""),
                "surname": get_field(client, "surname", ""),
                "extradata": get_field(client, "extradata", ""),
                "birthday": to_date(get_field(client, "birthday")),
                "birthday_place": get_field(client, "birthday_place", ""),
                "phone": get_field(client, "phone", ""),
                "email": get_field(client, "email", ""),
                "social": get_field(client, "social", ""),
                "address": get_field(client, "address", ""),
                "doc_title": get_field(client, "doc_title", ""),
                "doc_series": get_field(client, "doc_series", ""),
                "doc_code": get_field(client, "doc_code", ""),
                "doc_when": to_date(get_field(client, "doc_when")),
                "doc_valid": to_date(get_field(client, "doc_valid")),
                "doc_where": get_field(client, "doc_where", ""),
                "comment": get_field(client, "comment", ""),
                "anketa": get_field(client, "anketa", ""),
                "bl": to_bool(get_field(client, "bl")),
                "vip": to_bool(get_field(client, "vip")),
                "adv": to_bool(get_field(client, "adv")),
                "gender": to_int(get_field(client, "gender")),
                "foreigner": to_bool(get_field(client, "foreigner")),
                "is_live": to_bool(get_field(client, "is_live")),
                "pref": to_int(get_field(client, "pref"))
            })
        except Exception as e:
            print(f"Ошибка при вставке клиента {client.get('id')}: {e}")
    try:
        conn.commit()
    except Exception as e:
        print(f"Ошибка при коммите: {e}")
    finally:
        cur.close()
        conn.close()
else:
    print("Нет данных для записи или не удалось подключиться к базе.") 