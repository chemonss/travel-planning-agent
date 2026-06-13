# Tools layer

Этот документ описывает слой доступа к данным для `travel-planning-agent`.

Слой `tools` отвечает за:

* чтение профилей путешественников и групп;
* поиск перелётов;
* поиск отелей;
* поиск пакетных туров;
* расчёт бюджета;
* сборку готовых вариантов поездки для агента.

Главный интерфейс этого слоя:


```python
from travel_agent.tools.trip_options import get_trip_options_for_group

result = get_trip_options_for_group("G-0001")

best_flight = result["best"]["flight"]
best_hotel = result["best"]["hotel"]
best_tour = result["best"]["tour"]
recommended_option = result["recommended_option"]
```

---

# 1. Database

Файл:

```text
src/travel_agent/tools/db.py
```

## `TravelDatabase`

Read-only wrapper над SQLite-базой.

По умолчанию используется база:

```text
data/travelers/travelers.sqlite
```

Пример использования:

```python
from travel_agent.tools.db import TravelDatabase

db = TravelDatabase()
rows = db.fetch_all(
    "SELECT * FROM flights WHERE destination = ?",
    ("IST",),
)
```

## `fetch_one(query, params=())`

Возвращает одну строку как `dict` или `None`.

Пример:

```python
row = db.fetch_one(
    "SELECT * FROM travel_groups WHERE group_id = ?",
    ("G-0001",),
)
```

## `fetch_all(query, params=())`

Возвращает список строк как `list[dict]`.

Пример:

```python
rows = db.fetch_all(
    "SELECT * FROM hotels WHERE destination = ?",
    ("IST",),
)
```

Ограничение: разрешены только `SELECT`-запросы.

---

# 2. Groups

Файл:

```text
src/travel_agent/tools/groups.py
```

## `get_group(group_id)`

Возвращает параметры группы.

Пример:

```python
get_group("G-0001")
```

Пример результата:

```python
{
    "group_id": "G-0001",
    "origin_city": "Moscow",
    "destination": "IST",
    "start_date": "2026-07-10",
    "end_date": "2026-07-15",
    "budget_rub": 180000,
    "group_comment": "Семья с ребёнком, без ночных прилётов",
}
```

## `get_group_members(group_id)`

Возвращает участников группы вместе с профилями путешественников.

Пример:

```python
get_group_members("G-0001")
```

Пример результата:

```python
[
    {
        "group_id": "G-0001",
        "traveler_id": "T-0001",
        "role_in_group": "parent",
        "full_name": "Иван Петров",
        "age": 38,
        "citizenship": "RU",
        "home_airport": "SVO",
        "loyalty_program": "Aeroflot Bonus",
        "notes": "Предпочитает утренние, но не слишком ранние вылеты",
    },
    ...
]
```

## `get_group_preferences(group_id)`

Возвращает структурированные предпочтения участников группы.

Пример:

```python
get_group_preferences("G-0001")
```

Пример результата:

```python
[
    {
        "group_id": "G-0001",
        "traveler_id": "T-0001",
        "preference_type": "departure_time",
        "preference_value": "daytime",
        "comment": "Избегает вылетов до 06:00",
    },
    ...
]
```

## `get_full_group_profile(group_id)`

Главная функция для получения полного контекста группы.

Пример:

```python
get_full_group_profile("G-0001")
```

Пример результата:

```python
{
    "group": {...},
    "members": [...],
    "preferences": [...],
    "summary": {
        "group_id": "G-0001",
        "origin_city": "Moscow",
        "destination": "IST",
        "start_date": "2026-07-10",
        "end_date": "2026-07-15",
        "nights": 5,
        "budget_rub": 180000,
        "traveler_count": 3,
        "has_children": True,
    },
}
```

---

# 3. Flights

Файл:

```text
src/travel_agent/tools/flights.py
```

## `search_flights(...)`

Ищет перелёты по жёстким ограничениям.

Пример:

```python
search_flights(
    origin_city="Moscow",
    destination="IST",
    max_price_rub=None,
    baggage_required=True,
    direct_only=False,
    avoid_early_departure=True,
    avoid_night_arrival=True,
)
```

Учитываемые параметры:

* `origin_city` — город вылета;
* `destination` — направление;
* `max_price_rub` — максимальная цена перелёта;
* `baggage_required` — нужен ли включённый багаж;
* `direct_only` — только прямые рейсы;
* `avoid_early_departure` — исключать вылеты до 07:00;
* `avoid_night_arrival` — исключать прилёты после 23:00.

Возвращает список перелётов.

## `search_flights_for_group(group_id)`

Главная функция для поиска перелётов по группе.

Пример:

```python
search_flights_for_group("G-0001")
```

Возвращает ранжированный список кандидатов.

Для `G-0001` ожидаемый первый результат:

```python
{
    "flight_id": "FL-102",
    "origin_city": "Moscow",
    "destination": "IST",
    ...
}
```

Для `G-0003` ожидаемый первый результат:

```python
{
    "flight_id": "FL-311",
    ...
}
```

Для `G-0004` ожидаемый первый результат:

```python
{
    "flight_id": "FL-412",
    ...
}
```

## `rank_flights(flights, budget_sensitive=False)`

Ранжирует перелёты.

Учитывает:

* цену;
* багаж;
* пересадки;
* ранний вылет;
* ночной прилёт;
* тип тарифа;
* бюджетную чувствительность группы.

## `infer_flight_constraints_from_group(group_profile)`

Извлекает ограничения по перелёту из профиля группы, комментариев и предпочтений.

Возвращает:

```python
{
    "origin_city": "Moscow",
    "destination": "IST",
    "baggage_required": True,
    "avoid_night_arrival": True,
    "avoid_early_departure": True,
    "direct_only": False,
    "budget_sensitive": False,
}
```

---

# 4. Hotels

Файл:

```text
src/travel_agent/tools/hotels.py
```

## `search_hotels(...)`

Ищет отели по ограничениям.

Пример:

```python
search_hotels(
    destination="IST",
    nights=5,
    max_total_price_rub=None,
    breakfast_required=True,
    free_cancellation_required=False,
    min_stars=4,
    min_rating=7.5,
)
```

Учитываемые параметры:

* `destination` — направление;
* `nights` — количество ночей;
* `max_total_price_rub` — максимальная общая стоимость проживания;
* `breakfast_required` — обязателен ли завтрак;
* `free_cancellation_required` — обязательна ли бесплатная отмена;
* `min_stars` — минимальное число звёзд;
* `min_rating` — минимальный рейтинг.

Возвращает список отелей.

Если передан `nights`, к каждому отелю добавляется:

```python
"total_price_rub": price_per_night_rub * nights
```

## `search_hotels_for_group(group_id)`

Главная функция для поиска отелей по группе.

Пример:

```python
search_hotels_for_group("G-0001")
```

Для `G-0001` ожидаемый первый результат:

```python
{
    "hotel_id": "HT-045",
    "destination": "IST",
    "total_price_rub": 56300,
    ...
}
```

Для `G-0002` ожидаемый первый результат:

```python
{
    "hotel_id": "HT-101",
    ...
}
```

## `get_hotel_by_id(hotel_id)`

Возвращает один отель по идентификатору.

Пример:

```python
get_hotel_by_id("HT-045")
```

## `rank_hotels(hotels)`

Ранжирует отели.

Учитывает:

* цену;
* рейтинг;
* звёзды;
* завтрак;
* бесплатную отмену;
* признаки из `notes`, например семейный номер, пляж, центр, шум.

---

# 5. Tours

Файл:

```text
src/travel_agent/tools/tours.py
```

## `get_tour_by_id(tour_id)`

Возвращает пакетный тур по идентификатору.

Пример:

```python
get_tour_by_id("TR-020")
```

Пример результата:

```python
{
    "tour_id": "TR-020",
    "destination": "DXB",
    "total_price_rub": 214700,
    "includes_flight": 1,
    "includes_transfer": 1,
    "hotel_id": "HT-101",
    "notes": "Пляжный пакетный тур для пары",
}
```

## `search_tours(...)`

Ищет пакетные туры по направлению и бюджету.

Пример:

```python
search_tours(
    destination="DXB",
    max_total_price_rub=220000,
    require_flight=True,
    require_transfer=False,
)
```

## `search_tours_for_group(group_id)`

Главная функция для поиска туров по группе.

Пример:

```python
search_tours_for_group("G-0002")
```

Для `G-0002` ожидаемый первый результат:

```python
{
    "tour_id": "TR-020",
    "hotel_id": "HT-101",
    ...
}
```

## `enrich_tour_with_hotel(tour)`

Добавляет к туру связанный отель.

Пример результата:

```python
{
    "tour_id": "TR-020",
    "hotel_id": "HT-101",
    "hotel": {
        "hotel_id": "HT-101",
        "destination": "DXB",
        ...
    },
}
```

## `compare_tour_vs_independent(tour, flight, hotel)`

Сравнивает пакетный тур с самостоятельной сборкой:

```text
flight + hotel
```

Тур считается экономически разумным, если он не дороже самостоятельной сборки более чем на 10%.

Пример результата:

```python
{
    "can_compare": True,
    "independent_total_price_rub": 202680,
    "tour_total_price_rub": 214700,
    "price_difference_rub": 12020,
    "tour_price_ratio": 1.0593,
    "tour_is_reasonable": True,
    "reason": "Tour is within 10 percent of independent booking.",
}
```

---

# 6. Budget

Файл:

```text
src/travel_agent/tools/budget.py
```

## `calculate_independent_trip_total(flight, hotel)`

Считает стоимость самостоятельной сборки:

```text
перелёт + отель
```

Пример:

```python
calculate_independent_trip_total(
    flight={"price_rub": 74200},
    hotel={"total_price_rub": 56300},
)
```

Результат:

```python
130500
```

## `calculate_package_trip_total(tour)`

Считает стоимость пакетного тура.

Пример:

```python
calculate_package_trip_total(
    tour={"total_price_rub": 214700},
)
```

Результат:

```python
214700
```

## `calculate_budget_gap(total_price_rub, budget_rub)`

Считает разницу между стоимостью и бюджетом.

Положительное значение означает превышение бюджета.

Отрицательное значение означает запас бюджета.

Пример:

```python
calculate_budget_gap(130500, 180000)
```

Результат:

```python
-49500
```

## `check_budget(total_price_rub, budget_rub)`

Проверяет, укладывается ли вариант в бюджет.

Пример:

```python
check_budget(130500, 180000)
```

Результат:

```python
True
```

## `build_independent_budget_summary(flight, hotel, budget_rub)`

Возвращает бюджетный summary для самостоятельной сборки.

Пример результата:

```python
{
    "option_type": "independent",
    "flight_id": "FL-102",
    "hotel_id": "HT-045",
    "total_price_rub": 130500,
    "budget_rub": 180000,
    "budget_ok": True,
    "budget_gap_rub": -49500,
}
```

## `build_package_budget_summary(tour, budget_rub)`

Возвращает бюджетный summary для пакетного тура.

Пример результата:

```python
{
    "option_type": "package",
    "tour_id": "TR-020",
    "hotel_id": "HT-101",
    "total_price_rub": 214700,
    "budget_rub": 220000,
    "budget_ok": True,
    "budget_gap_rub": -5300,
}
```

---

# 7. Trip options

Файл:

```text
src/travel_agent/tools/trip_options.py
```

## `get_trip_options_for_group(group_id)`

Главная функция всего tools-слоя.

Она собирает:

* профиль группы;
* кандидатов по перелётам;
* кандидатов по отелям;
* кандидатов по турам;
* лучший перелёт;
* лучший отель;
* лучший тур;
* самостоятельную сборку;
* пакетный вариант;
* рекомендованный вариант.

Пример:

```python
from travel_agent.tools.trip_options import get_trip_options_for_group

result = get_trip_options_for_group("G-0001")
```

Структура результата:

```python
{
    "group_profile": {...},
    "candidates": {
        "flights": [...],
        "hotels": [...],
        "tours": [...],
    },
    "best": {
        "flight": {...},
        "hotel": {...},
        "tour": None,
    },
    "options": {
        "independent": {...},
        "package": {...},
    },
    "recommended_option": {...},
}
```

Для `G-0001` ожидается:

```text
best.flight.flight_id = FL-102
best.hotel.hotel_id = HT-045
recommended_option.option_type = independent
```

Для `G-0002` ожидается:

```text
best.flight.flight_id = FL-205
best.hotel.hotel_id = HT-101
best.tour.tour_id = TR-020
recommended_option.option_type = package
```

## `get_best_candidate(candidates)`

Возвращает первого кандидата из ранжированного списка или `None`.

## `build_independent_option(flight, hotel, budget_rub)`

Собирает самостоятельный вариант:

```text
flight + hotel + budget summary
```

## `build_package_option(tour, flight, hotel, budget_rub)`

Собирает пакетный вариант:

```text
tour + budget summary + comparison with independent option
```

## `select_recommended_option(independent_option, package_option)`

Выбирает рекомендованный вариант.

Логика:

1. если пакетный тур доступен, укладывается в бюджет и не дороже самостоятельной сборки более чем на 10%, выбрать пакет;
2. иначе выбрать самостоятельную сборку, если она доступна и укладывается в бюджет;
3. иначе выбрать пакет, если он доступен и укладывается в бюджет;
4. иначе вернуть `None`.

---

# 8. Utility scripts

## `scripts/build_sqlite_from_csv.py`

Создаёт SQLite-базу из CSV-файлов.

Запуск:

```bash
python scripts/build_sqlite_from_csv.py
```

Результат:

```text
data/travelers/travelers.sqlite
```

## `scripts/inspect_db.py`

Печатает таблицы, колонки и первые строки.

Запуск:

```bash
python scripts/inspect_db.py
```

## `scripts/check_reference_recommendations.py`

Проверяет, совпадают ли первые рекомендации tools-слоя с reference-файлами.

Запуск:

```bash
python scripts/check_reference_recommendations.py
```

Ожидаемый результат:

```text
=== Summary ===
Flights: 6/6
Hotels:  6/6
Total:   12/12
```
