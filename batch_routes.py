import json
import os
import sys
from typing import Tuple, Optional, Dict, Any

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")             # 2GIS Routing API key
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")  # Yandex Geocoder API key

YANDEX_GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x"
ROUTING_URL = "https://routing.api.2gis.com/routing/7.0.0/global"

# ---------------------------------------------------------
#  ВСПОМОГАТЕЛЬНЫЕ
# ---------------------------------------------------------


def format_coord(value: float) -> str:
    """
    Приводим координату к строке с 6 знаками после запятой.
    Пример: 55.7558 -> "55.755800"
    """
    return f"{value:.6f}"


def normalize_coord_to_str(raw: Any) -> Optional[str]:
    """
    Преобразует входное значение координаты к строке.
    - Если None или пустая строка -> возвращает None
    - Если число -> форматирует с 6 знаками
    - Если строка -> возвращает как есть (обрезав пробелы)
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return format_coord(float(raw))
    s = str(raw).strip()
    if s == "":
        return None
    return s


# ---------------------------------------------------------
#  ЯНДЕКС ГЕОКОДЕР
# ---------------------------------------------------------


def yandex_geocode_forward(address: str) -> Tuple[float, float]:
    """
    Прямой геокодинг: адрес -> (lat, lon) через Яндекс.
    Возвращает float-координаты.
    """
    if not YANDEX_API_KEY:
        raise RuntimeError("Не задан YANDEX_API_KEY для геокодера Яндекс")

    params = {
        "apikey": YANDEX_API_KEY,
        "format": "json",
        "geocode": address,
        "results": 1,
        "lang": "ru_RU",
    }
    r = requests.get(YANDEX_GEOCODER_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    members = (
        data.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    if not members:
        raise ValueError(f"Яндекс не нашёл адрес: {address!r}")

    geo = members[0]["GeoObject"]
    pos = geo["Point"]["pos"]  # "37.617635 55.755814"
    lon_str, lat_str = pos.split()
    lat = float(lat_str)
    lon = float(lon_str)
    return lat, lon


def yandex_geocode_reverse(lat_str: str, lon_str: str) -> Optional[str]:
    """
    Обратный геокодинг: (lat, lon) -> адрес (строка) через Яндекс.
    Если не удалось — возвращает None.
    """
    if not YANDEX_API_KEY:
        return None

    geocode_param = f"{lon_str},{lat_str}"  # Яндекс: "lon,lat"

    params = {
        "apikey": YANDEX_API_KEY,
        "format": "json",
        "geocode": geocode_param,
        "results": 1,
        "lang": "ru_RU",
    }
    r = requests.get(YANDEX_GEOCODER_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()

    members = (
        data.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    if not members:
        return None

    meta = (
        members[0]["GeoObject"]
        .get("metaDataProperty", {})
        .get("GeocoderMetaData", {})
    )
    return meta.get("text")


# ---------------------------------------------------------
#  ОБРАБОТКА ТОЧЕК (ВАРИАНТ A)
# ---------------------------------------------------------


def ensure_coords_and_address(point: Dict[str, Any], label: str) -> Tuple[float, float]:
    """
    На входе point вида:
    {
        "address": ... или null,
        "lat": "55.755800" | 55.7558 | null,
        "lon": "37.617300" | 37.6173 | null
    }

    Логика:
    - Если есть координаты:
        - нормализуем к строке с 6 знаками
        - если нет address -> обратный геокодинг Яндекс, пишем адрес
        - возвращаем float(lat), float(lon)
    - Если координат нет, но есть address:
        - прямой геокодинг Яндекса
        - lat/lon пишем как строки с 6 знаками
        - возвращаем float(lat), float(lon)
    - Если нет ни адреса, ни координат -> ошибка
    """

    lat_str = normalize_coord_to_str(point.get("lat"))
    lon_str = normalize_coord_to_str(point.get("lon"))
    addr = point.get("address")

    has_coords = lat_str is not None and lon_str is not None
    has_addr = addr not in (None, "")

    # --- Есть координаты ---
    if has_coords:
        point["lat"] = lat_str
        point["lon"] = lon_str

        if not has_addr:
            try:
                rev_addr = yandex_geocode_reverse(lat_str, lon_str)
                if rev_addr:
                    point["address"] = rev_addr
            except Exception as e:
                print(
                    f"[WARN] Не удалось обратным геокодингом получить адрес для {label}: {e}",
                    file=sys.stderr,
                )

        return float(lat_str), float(lon_str)

    # --- Координат нет, но есть адрес ---
    if has_addr:
        lat, lon = yandex_geocode_forward(addr)
        lat_str = format_coord(lat)
        lon_str = format_coord(lon)
        point["lat"] = lat_str
        point["lon"] = lon_str
        return lat, lon

    # --- Нет ни того, ни другого ---
    raise ValueError(f"[{label}] Нет ни координат, ни адреса.")


# ---------------------------------------------------------
#  МАРШРУТИЗАЦИЯ 2ГИС (Routing API 7.0.0, БЕЗ ПРОБОК)
# ---------------------------------------------------------


def calculate_route_2gis(
    route_id: str, from_lat: float, from_lon: float, to_lat: float, to_lon: float
) -> Tuple[int, int]:
    """
    Строит маршрут через 2ГИС Routing API 7.0.0 (POST /routing/7.0.0/global).
    Без учёта пробок: route_mode = 'shortest'.

    Возвращает (distance_m, duration_s).
    """
    if not API_KEY:
        raise RuntimeError("Не задан API_KEY для 2GIS Routing API")

    body = {
        "points": [
            {"type": "stop", "lat": from_lat, "lon": from_lon},
            {"type": "stop", "lat": to_lat, "lon": to_lon},
        ],
        "locale": "ru",
        "transport": "driving",   # Car routing. Спокойно можно менять на другой тип, если в тарифе есть.
        "route_mode": "shortest"  # Кратчайший по расстоянию, без учёта пробок.
        # ВАЖНО: никаких output/output_type/traffic_mode здесь не передаём.
    }

    params = {"key": API_KEY}

    r = requests.post(ROUTING_URL, params=params, json=body, timeout=15)

    print(f"\n=== 2GIS ROUTE REQUEST [{route_id}] ===")
    print("STATUS:", r.status_code)
    print("BODY:", json.dumps(body, ensure_ascii=False))
    print("RESP TEXT:", r.text[:500])
    print("=====================================\n")

    if r.status_code != 200:
        raise RuntimeError(f"Ошибка 2GIS: HTTP {r.status_code} → {r.text}")

    data = r.json()

    try:
        route = data["result"][0]
    except Exception:
        raise RuntimeError(f"Не удалось разобрать ответ 2GIS (нет result[0]): {data}")

    # По документации есть total_distance и total_duration
    if "total_distance" not in route or "total_duration" not in route:
        raise RuntimeError(
            f"В ответе 2GIS нет total_distance/total_duration: {route}"
        )

    distance_m = int(route["total_distance"])
    duration_s = int(route["total_duration"])

    return distance_m, duration_s


# ---------------------------------------------------------
#  MAIN
# ---------------------------------------------------------


def main():
    input_file = "input_batch.json"
    output_file = "output_batch.json"

    with open(input_file, "r", encoding="utf-8") as f:
        input_data = json.load(f)

    routes = input_data.get("routes", [])
    result_routes = []

    for route in routes:
        route_id = route.get("id", "")
        print(f"== Обработка маршрута {route_id} ==")

        loading = dict(route.get("loading") or {})
        unloading = dict(route.get("unloading") or {})

        out_route = {
            "id": route_id,
            "loading": loading,
            "unloading": unloading,
            "distance_m": route.get("distance_m"),
            "duration_s": route.get("duration_s"),
            "error": None,
        }

        try:
            # 1) Координаты + адрес для точки загрузки
            from_lat, from_lon = ensure_coords_and_address(
                loading, f"{route_id} / loading"
            )

            # 2) Координаты + адрес для точки выгрузки
            to_lat, to_lon = ensure_coords_and_address(
                unloading, f"{route_id} / unloading"
            )

            # 3) Маршрут без пробок (shortest)
            distance_m, duration_s = calculate_route_2gis(
                route_id, from_lat, from_lon, to_lat, to_lon
            )
            out_route["distance_m"] = distance_m
            out_route["duration_s"] = duration_s

        except Exception as e:
            out_route["error"] = str(e)

        result_routes.append(out_route)

    output_data = {"routes": result_routes}
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)

    print(f"Готово. Результат записан в {output_file}")


if __name__ == "__main__":
    main()