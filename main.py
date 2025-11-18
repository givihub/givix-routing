import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")                 # 2GIS Routing API
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")   # Yandex Geocoder API

YANDEX_GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x"
ROUTING_URL = "https://routing.api.2gis.com/routing/7.0.0/global"


# ---------------------------------------------------------------
# 1) Геокодер Яндекса
# ---------------------------------------------------------------
def geocode_address(address: str):
    params = {
        "apikey": YANDEX_API_KEY,
        "format": "json",
        "geocode": address,
        "results": 1
    }

    r = requests.get(YANDEX_GEOCODER_URL, params=params)
    data = r.json()

    try:
        member = data["response"]["GeoObjectCollection"]["featureMember"]
        if not member:
            raise ValueError("Яндекс не нашёл объект.")

        pos = member[0]["GeoObject"]["Point"]["pos"]  # "37.617635 55.755814"
        lon, lat = pos.split(" ")
        return float(lat), float(lon)

    except Exception as e:
        raise ValueError(f"Ошибка геокодирования '{address}': {e}")


# ---------------------------------------------------------------
# 2) Координаты из адреса или напрямую
# ---------------------------------------------------------------
def ensure_coords(point: dict):
    if "lat" in point and "lon" in point:
        return float(point["lat"]), float(point["lon"])
    if "address" in point:
        return geocode_address(point["address"])
    raise ValueError("Нет координат и нет адреса!!!")


# ---------------------------------------------------------------
# 3) Построение маршрута 2ГИС Routing API 7.0.0 (POST!)
# ---------------------------------------------------------------
def calculate_route(from_coords, to_coords, params_input):
    """Строит маршрут через Routing API 2ГИС 7.0.0 (POST) + параметры грузовиков."""

    body = {
        "points": [
            {"lat": from_coords[0], "lon": from_coords[1]},
            {"lat": to_coords[0],  "lon": to_coords[1]}
        ],
        "transport": params_input.get("transport", "truck"),
        "filters": params_input.get("filters", []),
        "locale": params_input.get("locale", "ru"),
        "output": "detailed",
        "route_mode": params_input.get("route_mode", "fastest")
    }

    # Добавляем параметры грузовика (если есть)
    vehicle_params = params_input.get("vehicle_params", {})
    for key in ["height", "width", "length", "weight", "axle_weight", "hazard_class"]:
        value = vehicle_params.get(key)
        if value not in (None, "", "0", 0):
            body[key] = value

    # API ключ — ТОЛЬКО в query!
    params = {"key": API_KEY}

    print("\n=== POST TO 2GIS ===")
    print(json.dumps(body, indent=4, ensure_ascii=False))
    print("====================\n")

    r = requests.post(ROUTING_URL, params=params, json=body)

    print("=== RAW RESPONSE ===")
    print("STATUS:", r.status_code)
    print("TEXT:", r.text[:3000])
    print("====================\n")

    data = r.json()

    if "result" not in data:
        raise ValueError(f"Ошибка маршрутизации: {data}")

    route = data["result"][0]

    # Основные значения
    distance_m = route.get("total_distance", 0)
    duration_s = route.get("total_duration", 0)

    return distance_m, duration_s

# ---------------------------------------------------------------
# 4) main()
# ---------------------------------------------------------------
def main():
    with open("input.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    from_lat, from_lon = ensure_coords(data["from"])
    to_lat, to_lon = ensure_coords(data["to"])

    distance_m, duration_s = calculate_route(
        (from_lat, from_lon),
        (to_lat, to_lon),
        data
    )

    result = {
        "success": True,
        "from": {"lat": from_lat, "lon": from_lon},
        "to": {"lat": to_lat, "lon": to_lon},
        "distance_meters": distance_m,
        "distance_km": round(distance_m / 1000, 3),
        "duration_seconds": duration_s,
        "duration_minutes": round(duration_s / 60, 1)
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    print("\nГотово! Результат записан в output.json\n")


if __name__ == "__main__":
    main()