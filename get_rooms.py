import requests
import json
from env_settings import login, api_key

def get_rooms(room_id=None):
    """
    Получение списка номеров через API метод getRooms
    
    Args:
        room_id (int, optional): ID конкретного номера. Если не указан, возвращается список всех номеров
    
    Returns:
        dict: Ответ от API с информацией о номерах
    """
    
    # Базовый URL API
    base_url = "https://litepms.ru/api/getRooms"
    
    # Параметры авторизации
    params = {
        'login': login,
        'hash': api_key
    }
    
    # Добавляем room_id если указан
    if room_id is not None:
        params['room_id'] = room_id
    
    try:
        # Выполняем GET запрос
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Проверяем статус ответа
        
        # Парсим JSON ответ
        result = response.json()
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при выполнении запроса: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Ошибка при парсинге JSON ответа: {e}")
        return None

def print_rooms_info(rooms_data):
    """
    Вывод информации о номерах в удобном формате
    
    Args:
        rooms_data (dict): Данные о номерах от API
    """
    if not rooms_data or 'data' not in rooms_data:
        print("Нет данных для отображения")
        return
    
    rooms = rooms_data['data']
    
    if isinstance(rooms, list):
        print(f"Найдено номеров: {len(rooms)}")
        print("-" * 80)
        
        for i, room in enumerate(rooms, 1):
            print(f"Номер {i}:")
            print(f"  ID: {room.get('id', 'N/A')}")
            print(f"  Название: {room.get('name', 'N/A')}")
            print(f"  Категория ID: {room.get('cat_id', 'N/A')}")
            print(f"  Этаж ID: {room.get('floor_id', 'N/A')}")
            print(f"  Корпус ID: {room.get('corpus_id', 'N/A')}")
            print(f"  Описание: {room.get('descr', 'N/A')}")
            print(f"  Площадь: {room.get('area', 'N/A')}")
            print(f"  Количество мест: {room.get('person', 'N/A')}")
            print(f"  Дополнительные места: {room.get('person_add', 'N/A')}")
            print(f"  Активен: {'Да' if room.get('active') else 'Нет'}")
            print("-" * 80)
    else:
        # Если передан room_id, возвращается один номер
        room = rooms
        print("Информация о номере:")
        print(f"  ID: {room.get('id', 'N/A')}")
        print(f"  Название: {room.get('name', 'N/A')}")
        print(f"  Категория ID: {room.get('cat_id', 'N/A')}")
        print(f"  Этаж ID: {room.get('floor_id', 'N/A')}")
        print(f"  Корпус ID: {room.get('corpus_id', 'N/A')}")
        print(f"  Описание: {room.get('descr', 'N/A')}")
        print(f"  Площадь: {room.get('area', 'N/A')}")
        print(f"  Количество мест: {room.get('person', 'N/A')}")
        print(f"  Дополнительные места: {room.get('person_add', 'N/A')}")
        print(f"  Активен: {'Да' if room.get('active') else 'Нет'}")

def main():
    """
    Основная функция для демонстрации работы скрипта
    """
    print("=== Получение списка всех номеров ===")
    all_rooms = get_rooms()
    
    if all_rooms:
        if all_rooms.get('success'):
            print_rooms_info(all_rooms)
        else:
            print(f"Ошибка API: {all_rooms.get('message', 'Неизвестная ошибка')}")
    
    print("\n" + "="*80 + "\n")
    
    # Пример получения конкретного номера (замените на реальный ID)
    print("=== Получение информации о конкретном номере ===")
    # room_id = 1  # Раскомментируйте и укажите реальный ID номера
    # specific_room = get_rooms(room_id)
    # if specific_room:
    #     if specific_room.get('success'):
    #         print_rooms_info(specific_room)
    #     else:
    #         print(f"Ошибка API: {specific_room.get('message', 'Неизвестная ошибка')}")

if __name__ == "__main__":
    main() 