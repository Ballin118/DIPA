from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .ai_service import get_ai_payload, get_live_traffic_payload
from .models import CityMetric


@require_GET
def api_insights(request):
    return JsonResponse(get_ai_payload(), json_dumps_params={"ensure_ascii": False})


@require_GET
def api_traffic_live(request):
    return JsonResponse(get_live_traffic_payload(), json_dumps_params={"ensure_ascii": False})


def home(request):
    # Забираем все метрики из базы данных
    metrics = CityMetric.objects.all()
    
    # Создаем словарь для удобного доступа в шаблоне
    metrics_dict = {m.name.lower(): m for m in metrics}
    
    map_config = {
        "city": settings.MAP_CITY_NAME,
        "center": [settings.MAP_CENTER_LAT, settings.MAP_CENTER_LON],
        "zoom": settings.MAP_DEFAULT_ZOOM,
        "hotspot": {
            "coords": [settings.MAP_HOTSPOT_LAT, settings.MAP_HOTSPOT_LON],
            "title": "Зона внимания (транспорт)",
            "hint": "ул. Фурманова — нетипичное замедление",
        },
        "monitor": {
            "coords": [43.2380, 76.8800],
            "title": "Центр мониторинга DIPA",
            "hint": settings.MAP_CITY_NAME,
        },
    }

    context = {
        "metrics": metrics_dict,
        "project_name": "DIPA Smart City",
        "yandex_maps_api_key": settings.YANDEX_MAPS_API_KEY,
        "map_config": map_config,
    }
    return render(request, "index.html", context)