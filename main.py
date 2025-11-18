import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")

GEOCODER_URL = "https://catalog.api.2gis.com/3.0/geocoding/search"
ROUTING_URL = "https://routing.api.2gis.com/carrouting/7.0.0/global"


def geocode_address(address: str):
    """Геокодинг через Яндекс Геокодер (JSON формат)."""
    YA_URL = "https://geocode-maps.yandex.ru/1.x"

    params = {
        "apikey": YANDEX_API_KEY,
        "format": "json",
        "geocode": address,
        "results": 1
    }

    resp = requests.get(YA_URL, params=params).json()

    try:
        pos = resp["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
        lon, lat = pos.split(" ")
        return float(lat), float(lon)
    except Exception as e:
        raise ValueError(f"Яндекс не смог геокодировать адрес '{address}'. Ошибка: {e}")


def ensure_coords(point_data: dict):
    """Если есть адрес — превращаем его в координаты. Если есть координаты — просто возвращаем."""
    if "lat" in point_data and "lon" in point_data:
        return point_data["lat"], point_data["lon"]

    if "address" in point_data:
        return geocode_address(point_data["address"])

    raise ValueError("Нет ни координат, ни адреса")


def calculate_route(from_coords, to_coords, params_input):
    """Строит маршрут в 2ГИС с учётом всех опциональных параметров."""

    # БАЗОВЫЕ ОБЯЗАТЕЛЬНЫЕ ПАРАМЕТРЫ
    params = {
        "key": API_KEY,
        "points": f"{from_coords[1]},{from_coords[0]};{to_coords[1]},{to_coords[0]}"
    }

    # -----------------------------------------------------------
    # 1️⃣ ТИП ТРАНСПОРТА
    # -----------------------------------------------------------
    vehicle_type = params_input.get("vehicle", "truck")
    params["type"] = vehicle_type

    # -----------------------------------------------------------
    # 2️⃣ ПРОБКИ (enabled / disabled)
    # -----------------------------------------------------------
    traffic = params_input.get("traffic", "disabled")
    params["traffic"] = traffic

    # -----------------------------------------------------------
    # 3️⃣ ФИЛЬТРЫ (dirt_road, toll_road, ferry, …)
    # -----------------------------------------------------------
    filters_list = params_input.get("filters")
    if isinstance(filters_list, list) and len(filters_list) > 0:
        params["filters"] = ",".join(filters_list)

    # -----------------------------------------------------------
    # 4️⃣ ПРИОРИТЕТ (time / distance)
    # -----------------------------------------------------------
    priority = params_input.get("priority")
    if priority:
        params["priority"] = priority

    # -----------------------------------------------------------
    # 5️⃣ ЛОКАЛЬ
    # -----------------------------------------------------------
    locale = params_input.get("locale")
    if locale:
        params["locale"] = locale

    # -----------------------------------------------------------
    # 6️⃣ ВРЕМЯ UTC
    # -----------------------------------------------------------
    utc = params_input.get("utc")
    if utc:
        params["utc"] = utc

    # -----------------------------------------------------------
    # 7️⃣ ПАРАМЕТРЫ ГРУЗОВИКА (ГАБАРИТЫ)
    # -----------------------------------------------------------
    vehicle_params = params_input.get("vehicle_params", {})
    # параметры, которые можно передать
    valid_keys = ["height", "width", "length", "weight", "axle_weight", "hazard_class"]

    for key in valid_keys:
        value = vehicle_params.get(key)
        if value not in (None, "", 0, "0"):
            # передаём только если НЕ пусто
            params[key] = value

    # -----------------------------------------------------------
    # ОТПРАВКА ЗАПРОСА
    # -----------------------------------------------------------
    resp = requests.get(ROUTING_URL, params=params).json()

    if "result" not in resp:
        raise ValueError(f"Ошибка маршрутизации: {resp}")

    route = resp["result"][0]

    distance_m = route["distance"]
    duration_s = route["duration"]

    return distance_m, duration_s

    return distance_m, duration_s


def main():
    # 1. Читаем входной JSON
    with open("input.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2. Координаты точки А
    from_lat, from_lon = ensure_coords(data["from"])
    # 3. Координаты точки Б
    to_lat, to_lon = ensure_coords(data["to"])

    # 4. Вычисляем маршрут
    distance_m, duration_s = calculate_route(
        (from_lat, from_lon), (to_lat, to_lon),
        vehicle=data.get("vehicle", "truck")
    )

    # 5. Формируем ответ
    result = {
        "success": True,
        "from": {"lat": from_lat, "lon": from_lon},
        "to": {"lat": to_lat, "lon": to_lon},
        "distance_meters": distance_m,
        "distance_km": round(distance_m / 1000, 3),
        "duration_seconds": duration_s,
        "duration_minutes": round(duration_s / 60, 1)
    }

    # 6. Записываем output.json
    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    print("Готово! Результат записан в output.json")


if __name__ == "__main__":
    main()