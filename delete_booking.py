import psycopg2
from psycopg2 import OperationalError
from env_settings import db_host, db_port, db_name, db_user, db_password

def delete_booking_by_id(booking_id):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        cur = conn.cursor()
        cur.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
        conn.commit()
        print(f"Бронь с booking_id={booking_id} удалена.")
        cur.close()
        conn.close()
    except OperationalError as e:
        print(f"Ошибка подключения к базе данных: {e}")
    except Exception as e:
        print(f"Ошибка при удалении: {e}")

if __name__ == "__main__":
    ids = input("Введите booking_id для удаления (через запятую, если несколько): ")
    for booking_id in ids.split(","):
        booking_id = booking_id.strip()
        if booking_id.isdigit():
            delete_booking_by_id(int(booking_id))
        else:
            print(f"Некорректный booking_id: {booking_id}")