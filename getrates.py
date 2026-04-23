import requests
from env_settings import login, api_key

import requests

# Ваши реальные логин и API ключ
LOGIN = login
API_KEY = api_key

BASE_URL = "https://litepms.ru/api/getRoomRates"

def get_room_rates(room_id, from_date=None, to_date=None, login=LOGIN, api_key=API_KEY):
    if room_id is None:
        raise ValueError("room_id обязателен для запроса")

    params = {
        "login": login,
        "hash": api_key,
        "room_id": room_id,
    }

    if from_date is not None:
        params['from_date'] = from_date  # формат YYYY-MM-DD

    if to_date is not None:
        params['to_date'] = to_date      # формат YYYY-MM-DD

    response = requests.get(BASE_URL, params=params)
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    # Пример вызова: получить тарифы для номера с ID=123 за август 2025
    room_id = 69661
    from_date = "2025-09-01"
    to_date = "2025-12-31"

    rates = get_room_rates(room_id, from_date, to_date)
    print(rates)
