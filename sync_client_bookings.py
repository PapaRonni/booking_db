import requests
import psycopg2
from psycopg2 import OperationalError
from datetime import datetime
from env_settings import login, api_key, db_host, db_port, db_name, db_user, db_password
import logging
import logging.config
import json
from module import write_sync_log

# --------------- Logger settings
log_setup = json.load(open('log_settings.json', 'r', encoding='utf-8'))

logging.config.dictConfig(log_setup)
logger = logging.getLogger("sync_bookings")

LOGIN = login
API_KEY = api_key

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

def to_date(val):
    s = get_field(val, None) if isinstance(val, dict) else val
    if s in ('0000-00-00', '', None):
        return None
    try:
        return s[:10]  # 'YYYY-MM-DD'
    except Exception:
        return None

def to_timestamp(val):
    if isinstance(val, dict):
        s = get_field(val, None)
    else:
        s = val
    if not s or s in ('', None):
        return None
    return s  # psycopg2 сам преобразует строку

def get_field(d, key, default=None):
    if d is None:
        return default
    if key is None:
        return d
    return d.get(key, default)

# ----------------------------------------------------------------------------------------------------------------------
# Синхронизация клиентов
# ----------------------------------------------------------------------------------------------------------------------
def sync_clients(cur, conn):
    url = "https://litepms.ru/api/getClients"
    params = {
        "login": LOGIN,
        "hash": API_KEY
    }
    clients = []
    page = 1
    while True:
        params["page"] = str(page)
        try:
            response = requests.get(url, params=params)
            if response.status_code != 200:
                logger.error("Ошибка HTTP:", response.status_code, response.text)
                break
            data = response.json()
            if data.get("status") != "success":
                logger.error("Ошибка в ответе API:", data)
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
            logger.error(f"Ошибка при запросе к API: {e}")
            break
    if clients and cur and conn:
        for client in clients:
            try:
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
                logger.error(f"Ошибка при вставке клиента {client.get('id')}: {e}")
        try:
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка при коммите: {e}")
        logger.info(f"Синхронизация клиентов завершена. Всего: {len(clients)}")
    else:
        logger.error("Нет данных для записи или не удалось подключиться к базе.")

# ----------------------------------------------------------------------------------------------------------------------
# Синхронизация броней
# ----------------------------------------------------------------------------------------------------------------------
def sync_bookings(cur, conn):
    url = "https://litepms.ru/api/getBookings"
    params = {
        "login": LOGIN,
        "hash": API_KEY,
        "start": "2025-06-20",   # укажи нужный диапазон дат (last_update)
        "finish": datetime.now().strftime("%Y-%m-%d")
    }
    bookings_ids = []
    page = 1
    while True:
        params["page"] = str(page)
        response = requests.get(url, params=params)
        if response.status_code != 200:
            logger.error("Ошибка HTTP:", response.status_code, response.text)
            break
        data = response.json()
        if data.get("status") != "success":
            logger.error("Ошибка в ответе API:", data)
            break
        page_ids = data.get("data", [])
        if not page_ids:
            break
        bookings_ids.extend(page_ids)
        if page >= data.get("pages", 1):
            break
        page += 1
    id_list = [int(b['id']) for b in bookings_ids if 'id' in b]
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
                logger.error(f"Ошибка в ответе getBooking для id={booking_id}: {detail_data}")
        else:
            logger.error(f"Ошибка HTTP при getBooking для id={booking_id}: {resp.status_code}")
    logger.info(f"Загружено полных броней: {len(all_bookings)}")
    if all_bookings and cur and conn:
        for b in all_bookings:
            try:
                client_id = to_int(get_field(b, "client_id"))
                if client_id == 0:
                    logger.error(f"Пропущена бронь {b.get('id')} из-за client_id=0")
                    continue
                cur.execute("SELECT 1 FROM clients WHERE id = %s", (client_id,))
                if not cur.fetchone():
                    logger.error(f"Пропущена бронь {b.get('id')}: client_id {client_id} отсутствует в clients")
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
                logger.error(f"Ошибка при вставке брони {b.get('id')}: {e}")
                if conn:
                    conn.rollback()
        logger.info("Синхронизация закончена успешно.")
        write_sync_log(cur, conn, "INFO", "sync_bookings", "Синхронизация завершена успешно.")
    else:
        logger.error("Нет данных для записи или не удалось подключиться к базе.")
        write_sync_log(cur, conn, "ERROR", "sync_bookings", f"Синхронизация завершилась с ошибкой.")

if __name__ == "__main__":
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        cur = conn.cursor()
        logger.info("Синхронизация клиентов...")
        sync_clients(cur, conn)
        logger.info("Синхронизация броней...")
        sync_bookings(cur, conn)
        cur.close()
        conn.close()
    except OperationalError as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
