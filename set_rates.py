#!/root/miniconda3/envs/pms/bin/python
"""
Выставление тарифов на площадках (OTA) через веб-интерфейс LitePMS.
Данные о ценах — из Excel "Reka Oblaka Tarif.xlsx".

Интерактивно: сначала площадка, затем период. Или: --channel / LITEPMS_RATE_CHANNEL, --from-date / RATE_FROM.
Реализовано: Суточно, Путешествия, Броневик, Авито и Сайт (тариф «основной» → тарифные условия).
"""

import argparse
import re
import sys
import time
import logging
import calendar
import os
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from typing import Final

import openpyxl
from playwright.sync_api import Locator, sync_playwright, Page

import dotenv

dotenv.load_dotenv('.env')

LOG_FILE = 'set_rates.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

LITEPMS_LOGIN = os.environ['login']
LITEPMS_PASSWORD = os.environ['pass']

EXCEL_FILE = 'Reka Oblaka Tarif.xlsx'
EXTRA_GUEST_FEE = 500

# Переменная окружения: ключ канала (site, travel, avito, sutochno, bronevik)
ENV_SALES_CHANNEL = 'LITEPMS_RATE_CHANNEL'

# Страница списка номеров (тариф «основной» в колонке «Цена»)
LITEPMS_ROOMS_URL = 'https://litepms.ru/room'

# Стабильность headless Chromium (Linux / Docker / нехватка /dev/shm)
CHROMIUM_LAUNCH_ARGS: Final[tuple[str, ...]] = (
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--disable-gpu',
    '--disable-software-rasterizer',
)


@dataclass(frozen=True)
class SalesChannelConfig:
    """Настройки канала продаж: колонка надбавки в Excel и URL страницы тарифов LitePMS."""

    key: str
    title_ru: str
    # Индекс колонки в строке надбавок (строка 3 Excel): Путешествия=1, Авито=2, Суточно=3, Броневик=4, Сайт=5
    excel_surcharge_col: int
    litepms_rate_url: str
    implemented: bool
    date_to_exclusive: bool = False
    extra_guest_label: str = 'Доплата за каждого гостя'


SALES_CHANNELS: Final[dict[str, SalesChannelConfig]] = {
    'site': SalesChannelConfig(
        key='site',
        title_ru='Сайт',
        excel_surcharge_col=5,
        litepms_rate_url=LITEPMS_ROOMS_URL,
        implemented=True,
        extra_guest_label='Цены за дополнительное место',
    ),
    'travel': SalesChannelConfig(
        key='travel',
        title_ru='Путешествия',
        excel_surcharge_col=1,
        litepms_rate_url='https://litepms.ru/settings/channels/ota_rate_ytravel?id=49362&room_id=14888&object_id=4685',
        implemented=True,
        date_to_exclusive=True,
        extra_guest_label='Цена за сутки за доп. место',
    ),
    'avito': SalesChannelConfig(
        key='avito',
        title_ru='Авито',
        excel_surcharge_col=2,
        litepms_rate_url='https://litepms.ru/settings/channels/ota_rate_avito?id=11&object_id=4174',
        implemented=True,
        date_to_exclusive=True,
        extra_guest_label='Доплата за гостя',
    ),
    'sutochno': SalesChannelConfig(
        key='sutochno',
        title_ru='Суточно.ру',
        excel_surcharge_col=3,
        litepms_rate_url='https://litepms.ru/settings/channels/ota_rate_sutochno?id=9&object_id=4193',
        implemented=True,
    ),
    'bronevik': SalesChannelConfig(
        key='bronevik',
        title_ru='Броневик',
        excel_surcharge_col=4,
        litepms_rate_url='https://litepms.ru/settings/channels/ota_rate_bronevik?id=40140&room_id=15812&object_id=5243',
        implemented=True,
        date_to_exclusive=True,
        extra_guest_label='Цена за сутки за доп. место',
    ),
}

DEFAULT_SALES_CHANNEL_KEY: Final[str] = 'sutochno'

MONTH_NAMES_RU = {
    'ЯНВАРЬ': 1, 'ФЕВРАЛЬ': 2, 'МАРТ': 3, 'АПРЕЛЬ': 4,
    'МАЙ': 5, 'ИЮНЬ': 6, 'ИЮЛЬ': 7, 'АВГУСТ': 8,
    'СЕНТЯБРЬ': 9, 'ОКТЯБРЬ': 10, 'НОЯБРЬ': 11, 'ДЕКАБРЬ': 12,
}

# Необязательно: дата начала выставления цен из окружения (если не передан --from-date)
ENV_RATE_FROM = 'SUTOCHNO_RATE_FROM'


def parse_rate_from_string(s: str) -> date:
    """Парсит дату в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД."""
    s = s.strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f'Неверный формат даты: {s!r}. Используйте ДД.ММ.ГГГГ (например 01.06.2026) или ГГГГ-ММ-ДД.'
    )


def prompt_rate_from_interactive() -> date | None:
    """Запрашивает в консоли, с какой даты выставлять цены. None — без ограничения по дате."""
    print()
    print('Период выставления цен')
    print('  1 — По всем актуальным месяцам из Excel (ограничение только «прошлые месяцы» как раньше)')
    print('  2 — Только начиная с даты (уже выставленные раньше даты не трогать)')
    print()

    while True:
        choice = input('Выберите вариант [1]: ').strip() or '1'
        if choice == '1':
            return None
        if choice == '2':
            break
        print('Введите 1 или 2.')

    print()
    print('Формат даты: ДД.ММ.ГГГГ (например 01.06.2026) или ГГГГ-ММ-ДД.')
    while True:
        raw = input('Дата начала (включительно): ').strip()
        if not raw:
            print('Дата не может быть пустой. Повторите ввод или прервите Ctrl+C.')
            continue
        try:
            return parse_rate_from_string(raw)
        except ValueError as e:
            print(e)


def prompt_sales_channel_interactive() -> SalesChannelConfig:
    """Интерактивный выбор площадки."""
    print()
    print('Площадка для выставления цен')
    print('  1 — Путешествия')
    print('  2 — Авито')
    print('  3 — Суточно.ру')
    print('  4 — Броневик')
    print('  5 — Сайт (litepms.ru/room → тариф «основной» → тарифные условия)')
    print()

    choice_map = {
        '1': 'travel',
        '2': 'avito',
        '3': 'sutochno',
        '4': 'bronevik',
        '5': 'site',
    }
    while True:
        choice = input('Выберите площадку [3]: ').strip() or '3'
        key = choice_map.get(choice)
        if key:
            return SALES_CHANNELS[key]
        print('Введите число от 1 до 5.')


def resolve_sales_channel(cli_channel: str | None) -> SalesChannelConfig:
    """Канал: аргумент CLI, переменная окружения, меню в терминале или Суточно по умолчанию (не-TTY)."""
    if cli_channel:
        key = cli_channel.strip().lower()
        if key not in SALES_CHANNELS:
            raise ValueError(
                f'Неизвестный канал: {cli_channel!r}. Допустимо: {", ".join(sorted(SALES_CHANNELS))}.'
            )
        return SALES_CHANNELS[key]
    env_val = os.environ.get(ENV_SALES_CHANNEL, '').strip().lower()
    if env_val:
        if env_val not in SALES_CHANNELS:
            raise ValueError(
                f'{ENV_SALES_CHANNEL}={env_val!r} неизвестен. Допустимо: {", ".join(sorted(SALES_CHANNELS))}.'
            )
        return SALES_CHANNELS[env_val]
    if sys.stdin.isatty():
        return prompt_sales_channel_interactive()
    return SALES_CHANNELS[DEFAULT_SALES_CHANNEL_KEY]


def resolve_rate_from(cli_from_date: str | None) -> date | None:
    """Определяет дату старта: аргумент CLI, переменная окружения, интерактивный ввод или без ограничения."""
    if cli_from_date:
        return parse_rate_from_string(cli_from_date)
    env_val = os.environ.get('RATE_FROM', '').strip() or os.environ.get(ENV_RATE_FROM, '').strip()
    if env_val:
        return parse_rate_from_string(env_val)
    if sys.stdin.isatty():
        return prompt_rate_from_interactive()
    return None


@dataclass
class HolidayPeriod:
    date_from: date
    date_to: date
    price: float


@dataclass
class ApartmentRates:
    name: str
    weekday_price: float
    weekend_price: float
    holiday_periods: list[HolidayPeriod] = field(default_factory=list)


@dataclass
class MonthData:
    year: int
    month: int
    # Необязательное имя префикса для тарифных условий на сайте: ячейка в колонке B в строке с заголовком месяца (например май_01_03, июнь)
    condition_name_prefix: str | None = None
    apartments: list[ApartmentRates] = field(default_factory=list)


def parse_holiday_dates(header_text: str, year: int, month: int) -> tuple[date, date] | None:
    """Парсит диапазон праздничных дат из заголовка столбца.
    
    Форматы заголовков:
      - "Праздники\n6.03-8.03"
      - "Праздники\n1.05 - 3.05"
      - "Праздники\n8.04 - 7.05"
      - "Праздники\n(период 1)"  -> пропускаем (нет конкретных дат)
    """
    if not header_text:
        return None
    
    # Убираем слово "Праздники" и пробелы
    clean = header_text.replace('Праздники', '').replace('\n', ' ').strip()
    
    # Паттерн: d.mm - d.mm или d.mm-d.mm
    pattern = r'(\d{1,2})\.(\d{2})\s*[-–]\s*(\d{1,2})\.(\d{2})'
    m = re.search(pattern, clean)
    if not m:
        return None
    
    d1, mo1, d2, mo2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    
    # Определяем год для дат (может переходить через год)
    y1 = year
    y2 = year
    
    try:
        start = date(y1, mo1, d1)
        end = date(y2, mo2, d2)
        if end < start:
            end = date(y2 + 1, mo2, d2)
        return start, end
    except ValueError:
        return None


def parse_excel(
    filepath: str,
    rate_from: date | None = None,
    surcharge_col: int = 3,
) -> tuple[float, list[MonthData]]:
    """Парсит Excel-файл с тарифами.

    Если задан rate_from, месяцы, полностью заканчивающиеся до этой даты, пропускаются
    (не попадают в результат — скрипт не будет выставлять по ним цены).

    surcharge_col — индекс колонки надбавки для выбранного канала (см. SalesChannelConfig).

    Для канала «Сайт»: в строке с заголовком месяца (например «МАЙ 2026») колонка B — необязательный
    префикс названия тарифного условия (май_01_03, июнь и т.д.); к нему добавляются суффиксы
    _будни, _выходные, _праздник_N. В строке 3 Excel колонка с индексом 5 — надбавка «Сайт» (можно 0 или пусто).

    Returns:
        (channel_surcharge, list_of_month_data)
    """
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    # Строка 3 (индекс 2): надбавки для каналов продаж
    # Колонки: Канал продаж | Путешествия | Авито | Суточно | Броневик
    surcharge_row = rows[2]
    cell = surcharge_row[surcharge_col] if surcharge_col < len(surcharge_row) else None
    channel_surcharge = float(cell or 0)
    
    today = date.today()
    months: list[MonthData] = []
    
    i = 0
    while i < len(rows):
        row = rows[i]
        cell0 = str(row[0]).strip() if row[0] else ''
        
        # Ищем заголовок месяца (ЯНВАРЬ 2026, ФЕВРАЛЬ 2026, ...)
        month_match = None
        for month_name, month_num in MONTH_NAMES_RU.items():
            if cell0.startswith(month_name):
                year_match = re.search(r'(\d{4})', cell0)
                if year_match:
                    month_match = (month_num, int(year_match.group(1)))
                break
        
        if month_match:
            month_num, year = month_match
            month_start = date(year, month_num, 1)
            cond_b = row[1] if len(row) > 1 else None
            condition_prefix = (
                str(cond_b).strip()
                if cond_b is not None and str(cond_b).strip()
                else None
            )
            
            # Пропускаем месяцы, которые уже в прошлом (по первому дню месяца)
            last_day = calendar.monthrange(year, month_num)[1]
            month_end = date(year, month_num, last_day)
            
            if month_end < today:
                i += 1
                continue

            if rate_from is not None and month_end < rate_from:
                i += 1
                continue

            # Следующая строка - заголовок колонок с праздниками
            header_row = rows[i + 1] if i + 1 < len(rows) else None
            
            holiday_date_ranges = []
            if header_row:
                # Колонки: Номер | Будние | Выходные | Праздники1 | Праздники2 | Праздники3 | Примечание
                for col_idx in [3, 4, 5]:
                    h = str(header_row[col_idx]).strip() if header_row[col_idx] else ''
                    if h and 'Праздники' in h:
                        result = parse_holiday_dates(h, year, month_num)
                        holiday_date_ranges.append(result)  # None если нет дат
                    else:
                        holiday_date_ranges.append(None)
            
            # Следующие 19 строк - апартаменты
            month_data = MonthData(
                year=year,
                month=month_num,
                condition_name_prefix=condition_prefix,
            )
            
            for apt_row_idx in range(i + 2, min(i + 21, len(rows))):
                apt_row = rows[apt_row_idx]
                if not apt_row[0]:
                    break
                
                apt_name = str(apt_row[0]).strip()
                if not apt_name.startswith('Апартаменты'):
                    break
                
                weekday_price = apt_row[1]
                weekend_price = apt_row[2]
                
                # Если нет цены будней - апартамент не заполнен, пропускаем
                if weekday_price is None:
                    continue
                
                weekday_price = float(weekday_price)
                weekend_price = float(weekend_price) if weekend_price else weekday_price
                
                holidays = []
                for col_idx, date_range in enumerate([0, 1, 2]):
                    if col_idx < len(holiday_date_ranges) and holiday_date_ranges[col_idx]:
                        h_price = apt_row[3 + col_idx]
                        if h_price is not None:
                            start_dt, end_dt = holiday_date_ranges[col_idx]
                            holidays.append(HolidayPeriod(
                                date_from=start_dt,
                                date_to=end_dt,
                                price=float(h_price),
                            ))
                
                month_data.apartments.append(ApartmentRates(
                    name=apt_name,
                    weekday_price=weekday_price,
                    weekend_price=weekend_price,
                    holiday_periods=holidays,
                ))
            
            if month_data.apartments:
                months.append(month_data)
        
        i += 1
    
    return channel_surcharge, months


@dataclass
class RatePeriod:
    """Период для выставления одного тарифа в форме LitePMS."""
    date_from: date
    date_to: date
    weekdays: list[int]  # 0=пн, 1=вт, ..., 5=сб, 6=вс
    price: float
    # True для базового условия сайта (Пн–Вс, разная цена будни/выходные из Excel)
    is_base_month: bool = False


def build_rate_periods(
    month_data: MonthData,
    apt: ApartmentRates,
    surcharge: float,
    rate_from: date | None = None,
) -> list[RatePeriod]:
    """Строит список периодов для выставления тарифов для одного апартамента в одном месяце.

    Если задан rate_from, даты «от» не будут раньше этой даты (раньше выставленные цены не трогаем).

    Порядок: 1) будни, 2) выходные, 3) праздники — чтобы праздники перезаписывали базовые цены.
    """
    year = month_data.year
    month = month_data.month
    last_day = calendar.monthrange(year, month)[1]

    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    period_start = month_start
    if rate_from is not None:
        period_start = max(month_start, rate_from)

    if period_start > month_end:
        return []

    periods: list[RatePeriod] = []

    # 1. Будни месяца (пн-чт)
    if apt.weekday_price is not None:
        periods.append(RatePeriod(
            date_from=period_start,
            date_to=month_end,
            weekdays=[0, 1, 2, 3],
            price=apt.weekday_price + surcharge,
        ))

    # 2. Выходные месяца (пт-вс)
    if apt.weekend_price is not None:
        periods.append(RatePeriod(
            date_from=period_start,
            date_to=month_end,
            weekdays=[4, 5, 6],
            price=apt.weekend_price + surcharge,
        ))

    # 3. Праздничные периоды (все дни недели) — перезаписывают базовые цены
    for hp in apt.holiday_periods:
        p_start = max(hp.date_from, month_start)
        if rate_from is not None:
            p_start = max(p_start, rate_from)
        p_end = min(hp.date_to, month_end)
        if p_start <= p_end:
            periods.append(RatePeriod(
                date_from=p_start,
                date_to=p_end,
                weekdays=[0, 1, 2, 3, 4, 5, 6],
                price=hp.price + surcharge,
            ))
    
    return periods


MONTH_NUM_TO_RU_LOWER: Final[dict[int, str]] = {
    v: k.lower() for k, v in MONTH_NAMES_RU.items()
}


def build_site_rate_periods(
    month_data: MonthData,
    apt: ApartmentRates,
    surcharge: float,
    rate_from: date | None = None,
) -> list[RatePeriod]:
    """Для канала «Сайт»: одно базовое условие на весь месяц (Пн–Вс) + праздники.

    Базовое условие содержит все 7 дней; seven_prices_for_site_period заполнит разные
    цены для будней (Пн–Чт) и выходных (Пт–Вс) из Excel.
    Праздники идут поверх базового условия (LitePMS применяет последнее подходящее).
    """
    year = month_data.year
    month = month_data.month
    last_day = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    period_start = month_start
    if rate_from is not None:
        period_start = max(month_start, rate_from)
    if period_start > month_end:
        return []

    periods: list[RatePeriod] = []

    # 1. Базовый период — весь месяц, все дни (Пн–Вс), разные цены из Excel
    base_price = apt.weekday_price if apt.weekday_price is not None else (apt.weekend_price or 0)
    periods.append(RatePeriod(
        date_from=period_start,
        date_to=month_end,
        weekdays=list(range(7)),
        price=base_price + surcharge,
        is_base_month=True,
    ))

    # 2. Праздничные периоды (перезаписывают базовый через порядок условий)
    for hp in apt.holiday_periods:
        p_start = max(hp.date_from, month_start)
        if rate_from is not None:
            p_start = max(p_start, rate_from)
        p_end = min(hp.date_to, month_end)
        if p_start <= p_end:
            periods.append(RatePeriod(
                date_from=p_start,
                date_to=p_end,
                weekdays=list(range(7)),
                price=hp.price + surcharge,
            ))

    return periods


def build_site_condition_name(
    month_data: MonthData,
    period: RatePeriod,
    holiday_counter: int,
) -> str:
    """Имя тарифного условия на сайте: префикс из Excel (колонка B) + тип периода."""
    prefix = (month_data.condition_name_prefix or '').strip()
    m = MONTH_NUM_TO_RU_LOWER.get(month_data.month, str(month_data.month))
    if period.is_base_month:
        # Одно базовое условие на весь месяц (Пн–Вс, разные цены по дням)
        if prefix:
            return prefix
        return f'{m}_{period.date_from:%d.%m}_{period.date_to:%d.%m}'
    if period.weekdays == [0, 1, 2, 3]:
        kind = 'будни'
    elif period.weekdays == [4, 5, 6]:
        kind = 'выходные'
    else:
        kind = f'праздник_{holiday_counter}' if holiday_counter else 'праздник'
    if prefix:
        return f'{prefix}_{kind}'
    return f'{m}_{period.date_from:%d.%m}_{period.date_to:%d.%m}_{kind}'


def seven_prices_for_site_period(
    period: RatePeriod,
    apt: ApartmentRates,
    surcharge: float = 0,
) -> list[int]:
    """Семь цен пн–вс из Excel для сайта.

    Базовый период (is_base_month=True) или старые будни/выходные:
      Пн–Чт — будни, Пт–Вс — выходные из Excel + надбавка.
    Праздник: одна цена на все 7 дней.
    """
    wd = int(round((apt.weekday_price or 0) + surcharge))
    we = int(round((apt.weekend_price or 0) + surcharge))
    if period.is_base_month or period.weekdays in ([0, 1, 2, 3], [4, 5, 6]):
        return [wd, wd, wd, wd, we, we, we]
    hp = int(round(period.price))
    return [hp] * 7


class LitePMSAutomation:
    """Автоматизация браузера для выставления тарифов в LitePMS."""

    # Порядок дней соответствует порядку чекбоксов на странице
    WEEKDAY_NAMES = {
        0: 'понедельник',
        1: 'вторник',
        2: 'среда',
        3: 'четверг',
        4: 'пятница',
        5: 'суббота',
        6: 'воскресенье',
    }

    def __init__(self, page: Page, channel: SalesChannelConfig):
        self.page = page
        self._channel = channel
        self._rate_page_url = channel.litepms_rate_url
        self._current_room = ''
        # Чтобы не «висеть» на вечном ожидании селекторов / навигации
        page.set_default_timeout(45_000)
        page.set_default_navigation_timeout(60_000)

    def login(self, username: str, password: str):
        log.info('Авторизация в LitePMS...')
        self.page.goto('https://litepms.ru/login', timeout=60_000)
        self.page.wait_for_load_state('domcontentloaded')

        self.page.fill('input[name="username"]', username)
        self.page.fill('input[name="password"]', password)
        self.page.click('button[type="submit"], input[type="submit"]')
        self.page.wait_for_load_state('domcontentloaded')
        self.page.wait_for_timeout(2000)
        log.info('Авторизация выполнена.')

    def open_rate_page(self):
        self.page.goto(self._rate_page_url, timeout=60_000)
        self.page.wait_for_load_state('domcontentloaded')
        self.page.wait_for_timeout(2000)

    @staticmethod
    def _same_apartment_label(row_text: str, room_name: str) -> bool:
        """Совпадение «Апартаменты №N» без путаницы №1 / №10 (как в select_room)."""
        label = row_text.strip().lower()
        search = room_name.strip().lower()
        return (
            label.startswith(search + ' ')
            or label.startswith(search + '\t')
            or label.startswith(search + ' -')
            or label == search
        )

    def _open_site_main_rate(self, room_name: str) -> bool:
        """Со страницы /room открывает редактирование тарифа «основной» для номера."""
        page = self.page
        log.info('  [Сайт] Переход к списку номеров…')
        page.goto(LITEPMS_ROOMS_URL, timeout=60_000, wait_until='domcontentloaded')
        page.wait_for_timeout(500)

        # Один проход в JS: цикл по строкам с inner_text() давал до 45 с * число строк (зависание).
        search = room_name.strip()
        clicked = page.evaluate(
            """(search) => {
                const s = search.trim().toLowerCase();
                const same = (cell) => {
                    const label = cell.trim().toLowerCase();
                    return (
                        label === s ||
                        label.startsWith(s + ' ') ||
                        label.startsWith(s + '\\t') ||
                        label.startsWith(s + ' -')
                    );
                };
                const rows = document.querySelectorAll('tbody tr');
                for (const tr of rows) {
                    const tds = tr.querySelectorAll('td');
                    if (tds.length < 2) continue;
                    // Не полагаемся на индекс колонки: в LitePMS перед «Номер / Место» идут
                    // чекбокс, № п/п, ID — раньше брали tds[1] и сравнивали с «Апартаменты №1» зря.
                    let nameOk = false;
                    for (const td of tds) {
                        const cell = (td.textContent || '').trim();
                        if (same(cell)) {
                            nameOk = true;
                            break;
                        }
                    }
                    if (!nameOk) continue;
                    const links = tr.querySelectorAll('a');
                    for (const a of links) {
                        const t = (a.textContent || '').replace(/\\s+/g, ' ').trim();
                        if (/^основной$/i.test(t)) {
                            a.click();
                            return true;
                        }
                    }
                }
                return false;
            }""",
            search,
        )
        if not clicked:
            log.warning('  ВНИМАНИЕ: На странице номеров не найдена строка с «основной» для «%s».', room_name)
            return False

        log.info('  [Сайт] Клик по «основной», ожидаю экран редактирования тарифа…')
        # SPA может не дать второй domcontentloaded — ждём характерный текст страницы тарифа
        for hint in (
            'Название тарифа',
            'Редактирование тарифа',
            'Основные настройки',
        ):
            try:
                page.get_by_text(hint, exact=False).first.wait_for(state='visible', timeout=12_000)
                break
            except Exception:
                continue
        else:
            page.wait_for_timeout(2500)
        log.info('  Открыт тариф «основной» для: %s', room_name)
        return True

    def _open_rate_conditions_tab(self):
        page = self.page
        log.info('  [Сайт] Вкладка «Тарифные условия»…')
        add_pat = re.compile(r'Добавить\s+тарифн(ые|ое)\s+услови(я|е)', re.I)
        tab_pat = re.compile(r'^\s*Тарифные условия\s*$', re.I)

        try:
            page.wait_for_load_state('domcontentloaded', timeout=10_000)
        except Exception:
            page.wait_for_timeout(700)

        # Если нужный блок уже на экране, вкладку можно не нажимать.
        add_block = page.get_by_text(add_pat).first
        try:
            add_block.wait_for(state='visible', timeout=3_000)
            return
        except Exception:
            pass

        tab_candidates = [
            page.get_by_role('tab', name=tab_pat).first,
            page.get_by_role('link', name=tab_pat).first,
            page.get_by_role('button', name=tab_pat).first,
            page.locator('a, button, span, div, li').filter(has_text=tab_pat).first,
            page.get_by_text(tab_pat).first,
        ]

        clicked = False
        last_err = None
        for tab in tab_candidates:
            try:
                tab.wait_for(state='visible', timeout=4_000)
                try:
                    tab.click(timeout=8_000)
                except Exception:
                    tab.click(timeout=8_000, force=True)
                clicked = True
                break
            except Exception as e:
                last_err = e
                continue

        if not clicked:
            if last_err:
                raise last_err
            raise RuntimeError('Не найдена вкладка «Тарифные условия».')

        # На сайте обычно: «Добавить тарифное условие» (ед. ч.)
        try:
            add_block.wait_for(state='visible', timeout=15_000)
        except Exception:
            page.wait_for_timeout(900)

    def _click_add_rate_conditions(self) -> Page:
        """Кликаем «Добавить тарифное условие» и возвращаем страницу с формой.

        LitePMS открывает форму добавления условия в новом окне (window.open/target=_blank).
        Перехватываем новую страницу через context.expect_page().
        Если новое окно не появилось — возвращаем текущую страницу (SPA/навигация).
        """
        page = self.page
        log.info('  [Сайт] Кнопка «Добавить тарифное условие»…')
        add_pat = re.compile(r'Добавить.*тарифн.*услови', re.I)
        add = page.locator('a, button').filter(has_text=add_pat).first
        try:
            add.wait_for(state='visible', timeout=15_000)
        except Exception:
            add = page.get_by_text(add_pat).first
            add.wait_for(state='visible', timeout=10_000)

        # Перехватываем возможное новое окно (popup)
        url_before = page.url
        try:
            with page.context.expect_page(timeout=8_000) as popup_info:
                add.click(timeout=15_000)
            popup: Page = popup_info.value
            popup.wait_for_load_state('domcontentloaded', timeout=20_000)
            log.info('  [Сайт] Форма условия открылась в новом окне: %s', popup.url)
            return popup
        except Exception:
            # Новое окно не появилось — работаем на текущей странице
            try:
                page.wait_for_load_state('domcontentloaded', timeout=8_000)
            except Exception:
                page.wait_for_timeout(1200)
            url_after = page.url
            if url_after != url_before:
                log.info('  [Сайт] Форма условия: навигация на %s', url_after)
            else:
                log.info('  [Сайт] Форма условия: SPA/inline (URL без изменений).')
            return page

    def _fill_site_rate_condition(
        self,
        form_page: Page,
        period: RatePeriod,
        apt: ApartmentRates,
        title: str,
        extra_guest_fee: int = EXTRA_GUEST_FEE,
        surcharge: float = 0,
    ):
        """Форма нового тарифного условия: название, даты, 7 цен, 7 цен за доп. место.

        Не ищем контейнер по тексту «Новое тарифное условие» — этот текст может отсутствовать.
        Вместо этого работаем напрямую с видимыми полями страницы через JavaScript.
        form_page — страница с формой (попап или текущая, возвращённая _click_add_rate_conditions).
        """
        page = form_page
        log.info('    [Сайт] Заполняю поля нового тарифного условия…')

        main7 = seven_prices_for_site_period(period, apt, surcharge=surcharge)
        extra7 = [extra_guest_fee] * 7

        # Заполняем название условия.
        # Форма может использовать <td>, <div>, <span> вместо <label> для подписи поля.
        # Проверяем видимость через цепочку предков (не BoundingClientRect).
        filled_name = page.evaluate(
            """(title) => {
                const notHidden = (el) => {
                    let node = el;
                    while (node && node !== document.body) {
                        const st = getComputedStyle(node);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        node = node.parentElement;
                    }
                    return true;
                };
                const fillInp = (inp) => {
                    if (!inp || inp.type === 'hidden' || !notHidden(inp)) return false;
                    inp.scrollIntoView({ block: 'center' });
                    inp.focus();
                    inp.value = title;
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                };
                // Перебираем ВСЕ возможные теги-подписи для поля «Название»
                const tags = 'label,td,th,div,span,p,dt,legend,li,b,strong';
                for (const el of document.querySelectorAll(tags)) {
                    const t = (el.textContent || '').trim();
                    if (!/^Название/i.test(t) || t.length > 50) continue;
                    if (!notHidden(el)) continue;
                    // 1) label[for]
                    if (el.htmlFor) {
                        const inp = document.getElementById(el.htmlFor);
                        if (fillInp(inp)) return true;
                    }
                    // 2) следующий td → первый input внутри
                    const nextTd = el.nextElementSibling;
                    if (nextTd) {
                        const inp = nextTd.tagName === 'INPUT'
                            ? nextTd
                            : nextTd.querySelector('input:not([type="hidden"])');
                        if (fillInp(inp)) return true;
                    }
                    // 3) первый input в nextSibling-цепочке
                    let sib = el.nextSibling;
                    while (sib) {
                        if (sib.tagName === 'INPUT' && fillInp(sib)) return true;
                        sib = sib.nextSibling;
                    }
                }
                // Последний шанс: известные name-атрибуты
                for (const sel of ['input[name="name"]', 'input[name="title"]',
                                   'input[name="condition_name"]', 'input[name="cond_name"]']) {
                    for (const inp of document.querySelectorAll(sel)) {
                        if (fillInp(inp)) return true;
                    }
                }
                return false;
            }""",
            title,
        )
        if not filled_name:
            page.screenshot(path='error_site_name.png')
            raise RuntimeError('Не найден input для названия условия (проверьте error_site_name.png).')
        log.info('    [Сайт] Название условия заполнено: %s', title)

        # Заполняем даты через Playwright (нужны dispatchEvent + Tab для маски DD-MM-YYYY)
        try:
            df_loc = self._find_visible_date_input('Дата от', page)
            self._fill_date_input(df_loc, period.date_from)
            dt_loc = self._find_visible_date_input('Дата по', page)
            if dt_loc is None:
                dt_loc = self._find_visible_date_input('Дата до', page)
            if dt_loc is not None:
                self._fill_date_input(dt_loc, period.date_to)
        except Exception as e:
            log.error('    Ошибка дат условия: %s', e)
            page.screenshot(path='error_site_dates.png')
            raise

        filled = page.evaluate(
            """([main7, extra7]) => {
                const vis = (el) => {
                    if (!el) return false;
                    const st = getComputedStyle(el);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 2 && r.height > 2;
                };
                // Берём все видимые таблицы с днями недели (Пн/Понедельник)
                const inpVis = (i) => {
                    if (!i || i.disabled) return false;
                    const st = getComputedStyle(i);
                    if (st.display === 'none' || st.visibility === 'hidden') return false;
                    const r = i.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };
                const hasDays = (t) => /Понедельник|\\bПн\\b/i.test(t.textContent || '');
                const priceTables = Array.from(document.querySelectorAll('table'))
                    .filter(t => vis(t) && hasDays(t));
                const textInputs = (tbl) =>
                    Array.from(tbl.querySelectorAll('input')).filter(
                        (i) =>
                            inpVis(i) &&
                            (i.type === 'text' || i.type === '' || !i.type)
                    );
                if (priceTables.length >= 1) {
                    const ins = textInputs(priceTables[0]);
                    for (let k = 0; k < Math.min(7, ins.length); k++) {
                        ins[k].value = String(main7[k]);
                        ins[k].dispatchEvent(new Event('input', { bubbles: true }));
                        ins[k].dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
                let extraTbl = priceTables.find((t) =>
                    /дополнительн/i.test(t.textContent || '')
                );
                if (!extraTbl && priceTables.length >= 2) {
                    extraTbl = priceTables[1];
                }
                if (extraTbl) {
                    const ins2 = textInputs(extraTbl);
                    for (let k = 0; k < Math.min(7, ins2.length); k++) {
                        ins2[k].value = String(extra7[k]);
                        ins2[k].dispatchEvent(new Event('input', { bubbles: true }));
                        ins2[k].dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
                return true;
            }""",
            [main7, extra7],
        )
        if not filled:
            log.warning('    Не удалось заполнить таблицы цен через JS — проверьте форму.')

    def _save_site_rate_condition(self, form_page: Page) -> None:
        """Сохраняем условие и закрываем попап (если он был открыт)."""
        page = form_page
        btn = page.get_by_role('button', name='Сохранить', exact=True)
        if btn.count() == 0:
            btn = page.locator('input[type="submit"][value="Сохранить"]')
        if btn.count() == 0:
            btn = page.locator('button').filter(has_text=re.compile(r'^Сохранить$'))
        if btn.count() == 0:
            btn = page.locator('input[type="submit"]')
        if btn.count() == 0:
            raise RuntimeError('Не найдена кнопка «Сохранить».')
        btn.first.click(timeout=30_000)
        # Если форма была в попапе, он может закрыться автоматически сразу после сохранения.
        if page is not self.page:
            auto_closed = False
            try:
                page.wait_for_load_state('domcontentloaded', timeout=8_000)
            except Exception:
                pass
            try:
                page.wait_for_timeout(600)
            except Exception:
                auto_closed = True

            if page.is_closed() or auto_closed:
                log.info('    [Сайт] Попап закрылся автоматически после сохранения.')
            else:
                try:
                    page.close()
                    log.info('    [Сайт] Попап с формой условия закрыт.')
                except Exception:
                    pass
            # Даём основной странице время обновить список условий
            self.page.wait_for_timeout(1000)
            return

        try:
            page.wait_for_load_state('domcontentloaded', timeout=15_000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(1200)
        except Exception:
            pass

    def set_site_rate(
        self,
        period: RatePeriod,
        apt: ApartmentRates,
        month_data: MonthData,
        title: str,
        extra_guest_fee: int = EXTRA_GUEST_FEE,
        surcharge: float = 0,
        *,
        from_apartment_list: bool = True,
    ):
        """Тарифное условие на сайте.

        Первый период апартамента: список номеров → «основной» → вкладка «Тарифные условия» → Добавить → … → Сохранить.
        Следующие периоды того же апартамента: только «Добавить тарифные условия» → заполнить → Сохранить (без /room).
        Следующий апартамент снова начинается со списка номеров.
        """
        if from_apartment_list:
            if not self._open_site_main_rate(apt.name):
                raise RuntimeError(f'Не открыт тариф для {apt.name}')
            self._open_rate_conditions_tab()
        else:
            log.info('    [Сайт] Следующее условие того же номера — без перехода к списку апартаментов.')
        form_page = self._click_add_rate_conditions()
        self._fill_site_rate_condition(
            form_page,
            period,
            apt,
            title,
            extra_guest_fee=extra_guest_fee,
            surcharge=surcharge,
        )
        self._save_site_rate_condition(form_page)

    def select_room(self, room_name: str) -> bool:
        """Выбирает номер из выпадающего списка по имени.
        
        Сопоставление по точному вхождению "Апартаменты №X " (с пробелом или дефисом после)
        чтобы "№1" не совпадало с "№10".
        """
        select = self._find_select_by_label('Номер')
        if select.count() == 0:
            select = self.page.locator('select').first
        options = select.locator('option').all()
        search = room_name.lower()

        for opt in options:
            label = opt.inner_text().strip()
            label_lower = label.lower()
            # "Апартаменты №1 - ..." но не "Апартаменты №10 - ..."
            if label_lower.startswith(search + ' ') or label_lower.startswith(search + ' -') or label_lower == search:
                value = opt.get_attribute('value')
                select.select_option(value=value)
                log.info('  Выбран номер: %s', label)
                self.page.wait_for_timeout(1000)
                if self._channel.key in ('travel', 'bronevik'):
                    if not self._select_travel_tariff(room_name):
                        return False
                return True

        log.warning('  ВНИМАНИЕ: Номер "%s" не найден в списке!', room_name)
        return False

    def _find_select_by_label(self, label_text: str):
        """Ищет select по тексту соседнего label через for/id или через DOM."""
        label = self.page.locator(f'label:has-text("{label_text}")').first
        if label.count() == 0:
            return self.page.locator('select').filter(has_text=label_text).first
        for_attr = label.get_attribute('for')
        if for_attr:
            return self.page.locator(f'#{for_attr}')
        return self.page.locator(
            f'label:has-text("{label_text}") + select, label:has-text("{label_text}") ~ select'
        ).first

    def _wait_travel_form_after_room_change(self):
        """После смены номера поля «Тариф» могут дорисоваться с задержкой."""
        self.page.wait_for_timeout(800)
        try:
            self.page.wait_for_selector('text=Тариф', timeout=12000)
        except Exception:
            pass

    def _open_travel_tariff_dropdown(self) -> Locator | None:
        """Находит и открывает выпадающий список «Тариф» (multiselect). Возвращает locator кнопки или None."""
        page = self.page

        def _try_click(loc: Locator) -> Locator | None:
            if loc.count() == 0:
                return None
            try:
                loc.first.click(timeout=8000, force=True)
                return loc.first
            except Exception:
                try:
                    loc.first.click(timeout=8000, force=False)
                    return loc.first
                except Exception:
                    return None

        # 0) Первый multiselect с «Выбрано: N» в форме (или в main/content, если <form> нет)
        for scope in (
            page.locator('form').first,
            page.locator('main, article, .content, #content, .container-fluid').first,
        ):
            if scope.count() == 0:
                continue
            for sel in (
                scope.locator(
                    'button, [role="button"], .dropdown-toggle, .btn.multiselect, .btn-group > button, div.multiselect'
                ).filter(has_text=re.compile(r'Выбрано\s*:\s*\d', re.I)),
                scope.locator('.btn-group').filter(has_text=re.compile(r'Выбрано', re.I)),
            ):
                clicked = _try_click(sel)
                if clicked is not None:
                    return clicked

        # 1) LitePMS часто кладёт label «Тариф» и multiselect в соседних колонках (.row), без .form-group
        for sel in (
            page.locator(
                'xpath=//*[contains(., "Тариф")][self::label or self::span or self::div]'
                '[string-length(normalize-space(.)) < 40]/ancestor::div[contains(@class,"row")][1]//button'
            ),
            page.locator(
                'xpath=//label[contains(., "Тариф")]/ancestor::div[contains(@class,"row")][1]//button'
            ),
            page.locator(
                'xpath=//label[contains(., "Тариф")]/ancestor::*[contains(@class,"col")][1]//button'
            ),
            page.locator(
                'xpath=//label[contains(., "Тариф")]/ancestor::div[contains(@class,"form-group")][1]//button'
            ),
            page.locator('div.form-group').filter(has_text=re.compile(r'Тариф', re.I)).locator(
                'button, .dropdown-toggle, [role="button"], .btn.multiselect, .btn-group > button'
            ),
            page.locator('.form-group').filter(has_text=re.compile(r'Тариф', re.I)).locator(
                'button, .dropdown-toggle, [role="button"], .btn.multiselect'
            ),
            page.locator('xpath=//*[contains(., "Тариф")][self::label or self::span][1]/ancestor::*[contains(@class,"form-group")][1]//button'),
        ):
            clicked = _try_click(sel)
            if clicked is not None:
                return clicked

        # 2) Внутри основной формы первый multiselect с «Выбрано:» — обычно «Тариф» (у «Номер» часто native <select>)
        form_scope = page.locator('form').first
        if form_scope.count() > 0:
            for sel in (
                form_scope.locator(
                    'button, [role="button"], .dropdown-toggle, .btn.multiselect, a'
                ).filter(has_text=re.compile(r'Выбрано', re.I)),
            ):
                clicked = _try_click(sel)
                if clicked is not None:
                    return clicked

        # 3) Роль button по доступному имени (текст «Выбрано»)
        try:
            role_btn = page.get_by_role('button', name=re.compile(r'Выбрано', re.I)).first
            if role_btn.count() > 0:
                role_btn.click(timeout=5000)
                return role_btn
        except Exception:
            pass

        # 4) Любой кликабельный контрол с «Выбрано» на странице
        for sel in (
            page.locator(
                'button, [role="button"], .dropdown-toggle, .btn.multiselect, a'
            ).filter(has_text=re.compile(r'Выбрано', re.I)),
        ):
            if sel.count() == 0:
                continue
            first = sel.first
            try:
                first.click(timeout=5000)
                return first
            except Exception:
                continue

        # 5) JS: подпись может быть span/div; multiselect — не всегда <button>
        opened = page.evaluate(
            """() => {
                const form = document.querySelector('form') || document.body;

                const clickFirstSelected = (root) => {
                    const cand = Array.from(
                        root.querySelectorAll(
                            'button, [role="button"], .dropdown-toggle, .btn.multiselect, .multiselect, .btn-group > *'
                        )
                    )
                        .filter((el) => el && el.offsetParent !== null)
                        .filter((el) => {
                            const t = (el.innerText || el.textContent || '').trim();
                            return /Выбрано\\s*:\\s*\\d/.test(t) && t.length < 80;
                        });
                    if (cand.length) {
                        cand[0].click();
                        return true;
                    }
                    return false;
                };

                if (clickFirstSelected(form)) return true;

                const title = Array.from(
                    form.querySelectorAll('label, span, div, p, td, th, strong')
                ).find((el) => {
                    const t = (el.textContent || '').trim();
                    return /^Тариф\\s*:?$/i.test(t) || (t.includes('Тариф') && t.length < 30);
                });
                if (title) {
                    const row =
                        title.closest('.row') ||
                        title.closest('.form-horizontal') ||
                        title.closest('form') ||
                        title.parentElement;
                    if (row) {
                        let btn = row.querySelector(
                            'button, .dropdown-toggle, [role="button"], .btn-group button, .btn-group .multiselect'
                        );
                        if (!btn) {
                            btn = row.querySelector('.btn-group');
                        }
                        if (btn && btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                    }
                }

                const all = Array.from(
                    document.querySelectorAll('button, [role="button"], .dropdown-toggle, .multiselect')
                );
                const b = all.find(
                    (x) =>
                        x.offsetParent !== null &&
                        /Выбрано\\s*:/i.test((x.innerText || x.textContent || ''))
                );
                if (b) {
                    b.click();
                    return true;
                }
                return false;
            }"""
        )
        if opened:
            page.wait_for_timeout(200)
            btn = self._find_travel_tariff_close_button()
            if btn is not None:
                return btn
            alt = page.locator('button, .dropdown-toggle').filter(has_text=re.compile(r'Выбрано', re.I)).first
            if alt.count() > 0:
                return alt
            return None

        return None

    def _find_travel_tariff_close_button(self) -> Locator | None:
        """Кнопка того же выпадающего «Тариф» (повторный клик закрывает список)."""
        page = self.page
        for sel in (
            page.locator(
                'xpath=//label[contains(., "Тариф")]/ancestor::div[contains(@class,"row")][1]//button'
            ),
            page.locator(
                'xpath=//label[contains(., "Тариф")]/ancestor::*[contains(@class,"col")][1]//button'
            ),
            page.locator('div.form-group').filter(has_text=re.compile(r'Тариф', re.I)).locator(
                'button, .dropdown-toggle, [role="button"], .btn.multiselect, .btn-group > button'
            ),
            page.locator('.form-group').filter(has_text=re.compile(r'Тариф', re.I)).locator(
                'button, .dropdown-toggle, [role="button"], .btn.multiselect'
            ),
            page.locator('form').first.locator(
                'button, [role="button"], .dropdown-toggle, .btn.multiselect'
            ).filter(has_text=re.compile(r'Выбрано', re.I)),
            page.locator('button, [role="button"], .dropdown-toggle, .btn.multiselect').filter(
                has_text=re.compile(r'Выбрано', re.I)
            ),
        ):
            if sel.count() > 0:
                return sel.first
        try:
            rb = page.get_by_role('button', name=re.compile(r'Выбрано', re.I)).first
            if rb.count() > 0:
                return rb
        except Exception:
            pass
        return None

    def _select_travel_tariff(self, room_name: str) -> bool:
        """Для Путешествий обязательно выбирает тариф с тем же названием, что и номер."""
        self._wait_travel_form_after_room_change()

        # 1) Пытаемся через обычный select (если он доступен)
        tariff_select = self._find_select_by_label('Тариф')
        if tariff_select.count() > 0:
            options = tariff_select.locator('option').all()
            search = room_name.lower()
            for opt in options:
                label = opt.inner_text().strip()
                label_lower = label.lower()
                if label_lower.startswith(search + ' ') or label_lower.startswith(search + ' -') or label_lower == search:
                    value = opt.get_attribute('value')
                    tariff_select.select_option(value=value)
                    log.info('  Выбран тариф (select): %s', label)
                    self.page.wait_for_timeout(300)
                    return True

        # 2) Multiselect: открыть список
        dropdown_btn = self._open_travel_tariff_dropdown()
        if dropdown_btn is None:
            try:
                self.page.screenshot(path='error_tariff_dropdown_not_found.png', full_page=True)
            except Exception:
                pass
            log.warning('  ВНИМАНИЕ: Не найден блок "Тариф" для номера "%s".', room_name)
            return False

        self.page.wait_for_timeout(500)

        # Ищем чекбоксы в выпадающем списке (агрессивно: все видимые чекбоксы на странице)
        try:
            self.page.wait_for_selector('input[type="checkbox"]:visible', timeout=6000, state='visible')
        except Exception:
            pass
        self.page.wait_for_timeout(300)

        # Сначала пытаемся найти чекбокс именно для нашего номера (JS: checkbox + текст рядом)
        selected = self.page.evaluate(
            """(roomName) => {
                const search = roomName.toLowerCase();
                const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'))
                    .filter((cb) => cb.offsetParent !== null);

                for (const cb of checkboxes) {
                    const parent = cb.closest('li') || cb.closest('label') || cb.closest('.checkbox') || cb.parentElement;
                    if (!parent) continue;
                    const text = (parent.textContent || '').trim().toLowerCase();
                    if (text.includes('выделить все') || text.includes('select all')) continue;
                    if (
                        text === search ||
                        text.startsWith(search + ' ') ||
                        text.startsWith(search + ' -') ||
                        text.includes(search)
                    ) {
                        if (!cb.checked) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                        return parent.textContent.trim();
                    }
                }
                return null;
            }""",
            room_name,
        )

        if selected:
            log.info('  Выбран тариф (JS): %s', selected)
            self.page.wait_for_timeout(300)
            close_btn = self._find_travel_tariff_close_button()
            if close_btn:
                try:
                    close_btn.click(timeout=3000)
                except Exception:
                    pass
            self.page.wait_for_timeout(200)
            return True

        # Fallback: если точного совпадения нет, берём первый подходящий чекбокс (кроме "выделить все")
        fallback_selected = self.page.evaluate(
            """() => {
                const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'))
                    .filter((cb) => cb.offsetParent !== null);
                for (const cb of checkboxes) {
                    const parent = cb.closest('li') || cb.closest('label') || cb.closest('.checkbox') || cb.parentElement;
                    if (!parent) continue;
                    const text = (parent.textContent || '').trim().toLowerCase();
                    if (text.includes('выделить все') || text.includes('select all')) continue;
                    if (text.length > 0 && text.length < 200) {
                        if (!cb.checked) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                        return parent.textContent.trim();
                    }
                }
                return null;
            }"""
        )

        if fallback_selected:
            log.info('  Выбран тариф (fallback JS): %s', fallback_selected)
            self.page.wait_for_timeout(300)
            close_btn = self._find_travel_tariff_close_button()
            if close_btn:
                try:
                    close_btn.click(timeout=3000)
                except Exception:
                    pass
            self.page.wait_for_timeout(200)
            return True

        try:
            self.page.screenshot(path='error_tariff_no_checkbox.png', full_page=True)
        except Exception:
            pass
        close_btn = self._find_travel_tariff_close_button()
        if close_btn:
            try:
                close_btn.click(timeout=3000)
            except Exception:
                pass
        log.warning('  ВНИМАНИЕ: Не найден чекбокс тарифа для номера "%s".', room_name)
        return False

        close_btn = self._find_travel_tariff_close_button()
        if close_btn:
            close_btn.click()
        self.page.wait_for_timeout(200)
        return True

    def _fill_date_input(self, inp_locator, d: date):
        """Заполняет поле даты с использованием формата DD-MM-YYYY (маска поля)."""
        # Плейсхолдер в форме __-__-____, поэтому используем дефисы
        date_str = d.strftime('%d-%m-%Y')
        inp_locator.click(click_count=3)
        inp_locator.press_sequentially(date_str, delay=80)
        self.page.keyboard.press('Tab')

    def _find_input_by_label(self, label_text: str, root: Locator | None = None):
        """Ищет input по тексту соседнего label через for/id или через DOM."""
        base = root if root is not None else self.page
        label = base.locator(f'label:has-text("{label_text}")').first
        try:
            for_attr = label.get_attribute('for', timeout=1000)
        except Exception:
            for_attr = None
        if for_attr:
            return self.page.locator(f'#{for_attr}')
        # Fallback: следующий input после label
        return base.locator(
            f'label:has-text("{label_text}") + input, label:has-text("{label_text}") ~ input'
        ).first

    def _find_visible_date_input(self, label_text: str, page: Page | None = None) -> Locator | None:
        """Находит input для даты по тексту любого элемента-подписи (td, div, label…).

        Видимость проверяется через цепочку предков — не BoundingClientRect.
        """
        if page is None:
            page = self.page
        result = page.evaluate(
            """(label_text) => {
                const notHidden = (el) => {
                    let node = el;
                    while (node && node !== document.body) {
                        const st = getComputedStyle(node);
                        if (st.display === 'none' || st.visibility === 'hidden') return false;
                        node = node.parentElement;
                    }
                    return true;
                };
                const tags = 'label,td,th,div,span,p,dt,legend';
                for (const el of document.querySelectorAll(tags)) {
                    const t = (el.textContent || '').trim();
                    if (!t.startsWith(label_text) || t.length > 60) continue;
                    if (!notHidden(el)) continue;
                    if (el.htmlFor) return '#' + el.htmlFor;
                    const nextEl = el.nextElementSibling;
                    if (nextEl) {
                        if (nextEl.tagName === 'INPUT') return '__next__';
                        const inner = nextEl.querySelector('input:not([type="hidden"])');
                        if (inner && inner.id) return '#' + inner.id;
                        if (inner) return '__next__';
                    }
                    let sib = el.nextSibling;
                    while (sib) {
                        if (sib.tagName === 'INPUT') return '__next__';
                        sib = sib.nextSibling;
                    }
                }
                return null;
            }""",
            label_text,
        )
        if result == '__next__':
            return page.locator(
                f'label:has-text("{label_text}") + input,'
                f' label:has-text("{label_text}") ~ input'
            ).first
        if result:
            return page.locator(result)
        return None

    def _set_weekdays(self, weekdays: list[int]):
        """Устанавливает галочки дней недели (снимает все ненужные, ставит нужные)."""
        for day_idx, day_name in self.WEEKDAY_NAMES.items():
            cb = self.page.get_by_label(day_name)
            is_checked = cb.is_checked()
            should_check = day_idx in weekdays
            if is_checked != should_check:
                cb.set_checked(should_check)
            self.page.wait_for_timeout(100)

    def set_rate(self, period: RatePeriod, extra_guest_fee: int = EXTRA_GUEST_FEE):
        """Заполняет форму одного тарифа и сохраняет."""
        page = self.page
        date_from_str = period.date_from.strftime('%d.%m.%Y')
        date_to_str = period.date_to.strftime('%d.%m.%Y')
        price_str = str(int(period.price))
        date_to_ui = period.date_to
        if self._channel.date_to_exclusive:
            date_to_ui = period.date_to + timedelta(days=1)

        # --- Поля дат ---
        try:
            date_from_inp = self._find_input_by_label('Дата от')
            self._fill_date_input(date_from_inp, period.date_from)
        except Exception as e:
            log.error('    Ошибка при вводе даты "от": %s', e)
            page.screenshot(path=f'error_date_from_{date_from_str}.png')
            raise

        try:
            if self._channel.date_to_exclusive:
                # «Дата до» не включительно (Путешествия, Броневик, Авито и т.п.)
                date_to_inp = self._find_input_by_label('Дата до')
                if date_to_inp.count() == 0:
                    date_to_inp = self._find_input_by_label('Дата по')
            else:
                date_to_inp = self._find_input_by_label('Дата по')
                if date_to_inp.count() == 0:
                    date_to_inp = self._find_input_by_label('Дата до')
            self._fill_date_input(date_to_inp, date_to_ui)
        except Exception as e:
            log.error('    Ошибка при вводе даты "по": %s', e)
            page.screenshot(path=f'error_date_to_{date_to_str}.png')
            raise

        # --- Дни недели ---
        self._set_weekdays(period.weekdays)

        # --- Цена за сутки ---
        try:
            price_inp = self._find_input_by_label('Цена за сутки')
            price_inp.fill('')
            price_inp.type(price_str)
        except Exception as e:
            log.error('    Ошибка при вводе цены: %s', e)
            page.screenshot(path=f'error_price_{date_from_str}.png')
            raise

        # --- Доплата за гостя ---
        try:
            extra_inp = self._find_input_by_label(self._channel.extra_guest_label)
            extra_inp.fill('')
            extra_inp.type(str(extra_guest_fee))
        except Exception as e:
            log.error('    Ошибка при вводе доплаты за гостя: %s', e)
            page.screenshot(path=f'error_extra_{date_from_str}.png')
            raise

        # --- Сохранить ---
        save_btn = page.locator('button:has-text("Сохранить"), input[value="Сохранить"]').first
        save_btn.click()

        # Ждём реакции страницы: либо навигация, либо появление flash-сообщения
        try:
            page.wait_for_load_state('domcontentloaded', timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(2000)

        # Проверяем наличие сообщения об ошибке на странице
        error_visible = page.locator('text=ошибка, text=error, text=Error, .alert-danger, .error-message').count() > 0
        if error_visible:
            err_screenshot = f'error_save_{self._current_room.replace(" ", "_")}_{date_from_str}.png'
            page.screenshot(path=err_screenshot)
            log.error('    [ОШИБКА СОХРАНЕНИЯ] Обнаружено сообщение об ошибке. Скриншот: %s', err_screenshot)
        else:
            days_str = ', '.join(self.WEEKDAY_NAMES[d] for d in period.weekdays)
            log.info(
                '    [ВЫСТАВЛЕНО] %s | %s - %s | дни: [%s] | цена: %s руб. | доплата: %s руб.',
                self._current_room, date_from_str, date_to_str, days_str, price_str, extra_guest_fee,
            )

        # Ждём 7 секунд — обновление тарифа на канале происходит не мгновенно
        time.sleep(7)

        # Перезагружаем страницу для следующей записи
        self.open_rate_page()

    def process_apartment_month(
        self,
        apt: ApartmentRates,
        month_data: MonthData,
        surcharge: float,
        rate_from: date | None = None,
    ):
        """Обрабатывает все тарифы одного апартамента за один месяц."""
        month_name = [k for k, v in MONTH_NAMES_RU.items() if v == month_data.month][0]
        log.info('  Апартамент: %s (%s %d)', apt.name, month_name, month_data.year)
        self._current_room = apt.name

        periods = build_rate_periods(month_data, apt, surcharge, rate_from=rate_from)

        if self._channel.key == 'site':
            site_periods = build_site_rate_periods(month_data, apt, surcharge, rate_from=rate_from)
            holiday_counter = 0
            for period_idx, period in enumerate(site_periods):
                is_holiday = not period.is_base_month
                if is_holiday:
                    holiday_counter += 1
                title = build_site_condition_name(
                    month_data,
                    period,
                    holiday_counter if is_holiday else 0,
                )
                days_str = ', '.join(self.WEEKDAY_NAMES[d] for d in period.weekdays)
                log.info(
                    '    -> [Сайт] Условие «%s»: %s - %s, дни: [%s], цена: %d руб.',
                    title, period.date_from, period.date_to, days_str, int(period.price),
                )
                try:
                    self.set_site_rate(
                        period,
                        apt,
                        month_data,
                        title,
                        extra_guest_fee=EXTRA_GUEST_FEE,
                        surcharge=surcharge,
                        from_apartment_list=(period_idx == 0),
                    )
                except Exception as e:
                    log.error('    Ошибка выставления условия на сайте: %s', e)
                    try:
                        self.page.screenshot(path=f'error_site_{apt.name.replace(" ", "_")}.png', full_page=True)
                    except Exception:
                        pass
                    raise
                log.info(
                    '    [ВЫСТАВЛЕНО — сайт] %s | «%s» | %s - %s',
                    apt.name,
                    title,
                    period.date_from.strftime('%d.%m.%Y'),
                    period.date_to.strftime('%d.%m.%Y'),
                )
            return

        for period in periods:
            # Выбираем номер перед каждым тарифом, т.к. страница перезагружается после сохранения
            if not self.select_room(apt.name):
                return

            days_str = ', '.join(self.WEEKDAY_NAMES[d] for d in period.weekdays)
            log.info(
                '    -> Период: %s - %s, дни: [%s], цена: %d руб.',
                period.date_from, period.date_to, days_str, int(period.price),
            )
            self.set_rate(period)


def main():
    parser = argparse.ArgumentParser(
        description='Выставление тарифов на OTA из Excel в LitePMS.',
    )
    parser.add_argument(
        '--channel',
        '-c',
        choices=sorted(SALES_CHANNELS.keys()),
        metavar='КАНАЛ',
        help='Канал без меню в консоли: site, travel, avito, sutochno, bronevik.',
    )
    parser.add_argument(
        '--from-date',
        '-f',
        metavar='ДАТА',
        help='Не менять цены до этой даты (без меню в консоли). Форматы: ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.',
    )
    args = parser.parse_args()

    try:
        channel = resolve_sales_channel(args.channel)
    except ValueError as e:
        log.error('%s', e)
        sys.exit(1)

    if not channel.implemented:
        log.warning(
            'Площадка «%s» пока не реализована в скрипте.',
            channel.title_ru,
        )
        return

    rate_from = resolve_rate_from(args.from_date)

    started_at = datetime.now()
    log.info('=' * 60)
    log.info('Автоматическое выставление тарифов: %s', channel.title_ru)
    log.info('Запуск: %s', started_at.strftime('%Y-%m-%d %H:%M:%S'))
    if rate_from:
        log.info('Цены выставляются с даты: %s (раньше не трогаем)', rate_from.strftime('%d.%m.%Y'))
    log.info('=' * 60)

    log.info('Чтение файла %s...', EXCEL_FILE)
    surcharge, months = parse_excel(
        EXCEL_FILE,
        rate_from=rate_from,
        surcharge_col=channel.excel_surcharge_col,
    )
    log.info('Надбавка для %s: %g руб.', channel.title_ru, surcharge)
    log.info('Найдено месяцев с ценами: %d', len(months))

    if not months:
        log.warning('Нет месяцев с заполненными тарифами. Завершение.')
        return

    for m in months:
        month_name = [k for k, v in MONTH_NAMES_RU.items() if v == m.month][0]
        log.info('  %s %d: %d апартаментов', month_name, m.year, len(m.apartments))

    total_saved = 0

    with sync_playwright() as p:
        # slow_mo увеличивает время каждого шага; для стабильности оставляем 0
        browser = p.chromium.launch(
            headless=True,
            slow_mo=0,
            args=list(CHROMIUM_LAUNCH_ARGS),
        )
        try:
            context = browser.new_context()
            page = context.new_page()

            automation = LitePMSAutomation(page, channel)
            automation.login(LITEPMS_LOGIN, LITEPMS_PASSWORD)
            automation.open_rate_page()

            for month_data in months:
                month_name = [k for k, v in MONTH_NAMES_RU.items() if v == month_data.month][0]
                log.info('')
                log.info('--- %s %d ---', month_name, month_data.year)

                for apt in month_data.apartments:
                    periods_count = len(
                        build_rate_periods(month_data, apt, surcharge, rate_from=rate_from)
                    )
                    automation.process_apartment_month(
                        apt, month_data, surcharge, rate_from=rate_from
                    )
                    total_saved += periods_count

            elapsed = (datetime.now() - started_at).seconds
            log.info('')
            log.info('=' * 60)
            log.info('Готово. Выставлено записей тарифов: %d. Время работы: %d сек.', total_saved, elapsed)
            log.info('Лог сохранён в файл: %s', LOG_FILE)
            log.info('=' * 60)
        except Exception as e:
            log.exception(
                'Прерывание: %s. Если видите TargetClosedError — страница/браузер закрылись '
                '(часто из‑за нехватки памяти на огромном скриншоте или падения Chromium).',
                e,
            )
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    main()
