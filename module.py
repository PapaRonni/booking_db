def write_sync_log(cur, conn, level, logger_name, message):
    try:
        cur.execute("""
            INSERT INTO logs (level, logger, message)
            VALUES (%s, %s, %s)
        """, (level, logger_name, message))
        conn.commit()
    except Exception as e:
        print(f"Ошибка при записи лога в БД: {e}")