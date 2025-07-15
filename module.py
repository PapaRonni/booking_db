from datetime import datetime
from zoneinfo import ZoneInfo

def write_sync_log(cur, conn, level, logger_name, message):
    try:
        now_moscow = datetime.now(ZoneInfo("Europe/Moscow"))
        cur.execute("""
            INSERT INTO logs (log_time, level, logger, message)
            VALUES (%s, %s, %s, %s)
        """, (now_moscow, level, logger_name, message))
        conn.commit()
    except Exception as e:
        print(f"Ошибка при записи лога в БД: {e}")