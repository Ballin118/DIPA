"""
Локальный LLM через Ollama (qwen2.5:3b) + мок-данные и rule-based сигналы.
Если Ollama недоступна — ответ собирается из мока без сети.
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from django.conf import settings
from django.utils import timezone

from .models import CityMetric

# Город интерфейса — для согласования индекса с «ожидаемой» загрузкой дорог по часу
CITY_TZ = ZoneInfo("Asia/Almaty")


def traffic_time_scale(hour: int) -> float:
    """
    Множитель 0..1 для модели пробок по часу (0–23) в местном времени.
    Ночью и поздно вечером — заметно ниже, днём и в пик — около 1.
    """
    if 0 <= hour < 5:
        return 0.34 + hour * 0.02
    if hour == 5:
        return 0.44
    if 6 <= hour < 8:
        return 0.48 + (hour - 6) * 0.2
    if 8 <= hour < 10:
        return 0.72 + (hour - 8) * 0.14
    if 10 <= hour < 17:
        return 1.0
    if 17 <= hour < 20:
        return 1.0
    if 20 <= hour < 22:
        return 0.88 - (hour - 20) * 0.08
    if hour == 22:
        return 0.58
    return 0.42  # 23


def _almaty_hour(ts: float | None = None) -> int:
    if ts is None:
        return timezone.now().astimezone(CITY_TZ).hour
    return datetime.fromtimestamp(ts, tz=CITY_TZ).hour


def _metric_map() -> dict[str, CityMetric]:
    return {m.name.lower(): m for m in CityMetric.objects.all()}


def build_city_snapshot() -> dict[str, Any]:
    """Базовый мок + подмешивание значений из БД при наличии."""
    m = _metric_map()
    co2 = float(m["co2"].value) if "co2" in m else 420.0
    speed = float(m["speed"].value) if "speed" in m else 24.0
    noise = float(m["noise"].value) if "noise" in m else 68.0

    raw_index = max(15, min(95, 110 - speed * 1.2 + noise * 0.15))
    h = _almaty_hour()
    scale = traffic_time_scale(h)
    # Ночью тот же «сырой» расчёт даёт завышение — умножаем на суточный коэффициент
    traffic_index = max(15, min(95, round(raw_index * scale, 1)))

    return {
        "city": "Алматы",
        "traffic_index": traffic_index,
        "traffic_raw_index": round(raw_index, 1),
        "local_hour": h,
        "avg_speed_kmh": speed,
        "co2_ppm": co2,
        "noise_db": noise,
        "pm25_ugm3": 38.0,
        "wind_ms": 5.4,
        "safety_open_incidents": 2,
        "cctv_anomaly_score": 0.34,
        "water_pressure_bar": 3.8,
        "district_hotspot": "ул. Фурманова — нетипичное замедление",
    }


def _traffic_index_at(moment: float, baseline: float) -> float:
    """Индекс пробок в момент времени: база из метрик + плавные колебания + лёгкий шум."""
    h = _almaty_hour(moment)
    scale = traffic_time_scale(h)
    # Ночью меньше «дрожи» вокруг базы — иначе синус снова разгоняет до «дневных» значений
    wiggle = 0.35 + 0.65 * scale
    drift = wiggle * (
        2.8 * math.sin(moment / 95.0)
        + 1.4 * math.sin(moment / 28.0)
        + 0.7 * math.sin(moment / 17.0)
    )
    sec = int(moment * 1.2)
    jitter = wiggle * ((((sec * 7919) % 17) / 17.0 * 1.8 - 0.9))
    idx = baseline + drift + jitter
    return max(15.0, min(95.0, round(idx, 1)))


def get_live_traffic_payload() -> dict[str, Any]:
    """Текущий «живой» индекс и предыстория для графика (шаг 2.5 с, как на клиенте)."""
    snap = build_city_snapshot()
    baseline = float(snap["traffic_index"])
    now = time.time()
    step = 2.5
    points = 48
    history = [_traffic_index_at(now - (points - 1 - i) * step, baseline) for i in range(points)]
    idx = history[-1]
    prev = history[-2] if len(history) > 1 else idx
    delta = round(idx - prev, 1)

    if idx < 45:
        level = "low"
        label = "Свободно"
    elif idx < 65:
        level = "medium"
        label = "Умеренно"
    elif idx < 80:
        level = "high"
        label = "Пробки"
    else:
        level = "critical"
        label = "Критично"

    return {
        "index": idx,
        "delta": delta,
        "baseline": baseline,
        "avg_speed_kmh": snap["avg_speed_kmh"],
        "level": level,
        "label_ru": label,
        "history": history,
        "poll_interval_ms": 2500,
        "updated_at": timezone.now().isoformat(),
        "timezone": "Asia/Almaty",
        "local_hour": snap.get("local_hour", _almaty_hour()),
        "time_scale": traffic_time_scale(snap.get("local_hour", _almaty_hour())),
    }


def detect_incidents(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Правила отклонений и приоритетов (без LLM)."""
    out: list[dict[str, Any]] = []

    if snapshot["traffic_index"] >= 65:
        out.append(
            {
                "id": "traffic-1",
                "domain": "transport",
                "title": "Высокий индекс пробок",
                "priority": "high" if snapshot["traffic_index"] >= 75 else "medium",
                "detail": f"Индекс {snapshot['traffic_index']}: возможна перегрузка сети; проверить {snapshot['district_hotspot']}.",
            }
        )

    if snapshot["noise_db"] >= 65:
        out.append(
            {
                "id": "eco-noise",
                "domain": "ecology",
                "title": "Повышенный уровень шума",
                "priority": "high" if snapshot["noise_db"] >= 70 else "medium",
                "detail": f"{snapshot['noise_db']} дБ — выше комфортного порога для центра.",
            }
        )

    if snapshot["co2_ppm"] >= 430:
        out.append(
            {
                "id": "eco-co2",
                "domain": "ecology",
                "title": "CO₂ выше целевого диапазона",
                "priority": "medium",
                "detail": f"{snapshot['co2_ppm']} ppm — усилить мониторинг и вентиляцию зон скопления транспорта.",
            }
        )

    if snapshot["safety_open_incidents"] >= 2:
        out.append(
            {
                "id": "safe-1",
                "domain": "safety",
                "title": "Несколько открытых инцидентов безопасности",
                "priority": "high",
                "detail": "Требуется координация с оперативными службами и перераспределение патрулей.",
            }
        )

    if snapshot["water_pressure_bar"] < 4.0:
        out.append(
            {
                "id": "util-water",
                "domain": "utilities",
                "title": "Давление в сети на нижней границе нормы",
                "priority": "medium",
                "detail": f"{snapshot['water_pressure_bar']} бар — плановая проверка насосных узлов.",
            }
        )

    if not out:
        out.append(
            {
                "id": "ok-1",
                "domain": "system",
                "title": "Показатели в допустимых пределах",
                "priority": "low",
                "detail": "Существенных отклонений по мок-правилам не зафиксировано.",
            }
        )

    return out


def _parse_llm_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _fallback_executive(snapshot: dict[str, Any], incidents: list[dict[str, Any]]) -> dict[str, Any]:
    high = [i for i in incidents if i["priority"] == "high"]
    crit = "высокая" if high else "средняя" if any(i["priority"] == "medium" for i in incidents) else "низкая"
    what = (
        f"Агрегированное состояние: индекс пробок {snapshot['traffic_index']}, "
        f"шум {snapshot['noise_db']} дБ, CO₂ {snapshot['co2_ppm']} ppm. "
        f"Зафиксировано инцидентов: {len(incidents)}."
    )
    actions = []
    for i in incidents[:3]:
        if i["priority"] in ("high", "medium"):
            actions.append(f"[{i['domain']}] {i['title']}: усилить контроль и отработать по регламенту.")
    if not actions:
        actions.append("Поддерживать текущий режим мониторинга и плановые обходы.")
    return {
        "what": what,
        "criticality": crit,
        "actions": actions[:5],
        "eco_note": f"Ветер {snapshot['wind_ms']} м/с; PM2.5 оценочно {snapshot['pm25_ugm3']} µg/m³.",
        "traffic_note": snapshot["district_hotspot"],
    }


def call_ollama(messages: list[dict[str, str]]) -> str | None:
    base = getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = getattr(settings, "OLLAMA_MODEL", "qwen2.5:3b")
    timeout = getattr(settings, "OLLAMA_TIMEOUT", 120.0)
    url = f"{base}/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            msg = data.get("message") or {}
            content = msg.get("content")
            if content:
                return content
    except (httpx.HTTPError, OSError, ValueError):
        return None
    return None


def build_prompt(snapshot: dict[str, Any], incidents: list[dict[str, Any]]) -> str:
    inc_json = json.dumps(incidents, ensure_ascii=False)
    snap_json = json.dumps(snapshot, ensure_ascii=False)
    return f"""Ты аналитик Smart City. По данным снимка города и списку инцидентов дай управленческий вывод.

Снимок:
{snap_json}

Инциденты (правила):
{inc_json}

Ответь ТОЛЬКО одним JSON-объектом без пояснений и без markdown, ключи:
"what" — что происходит в городе одной строкой;
"criticality" — одно из: низкая, средняя, высокая;
"actions" — массив из 2–4 конкретных действий для властей;
"eco_note" — кратко про экологию/воздух;
"traffic_note" — кратко про транспорт.

Язык: русский."""


def get_ai_payload() -> dict[str, Any]:
    snapshot = build_city_snapshot()
    incidents = detect_incidents(snapshot)
    prompt = build_prompt(snapshot, incidents)

    raw = call_ollama([{"role": "user", "content": prompt}])
    source = "ollama"
    executive: dict[str, Any]

    if raw:
        parsed = _parse_llm_json(raw)
        if parsed and isinstance(parsed, dict) and "what" in parsed:
            actions_raw = parsed.get("actions") if isinstance(parsed.get("actions"), list) else []
            executive = {
                "what": str(parsed.get("what", "")),
                "criticality": str(parsed.get("criticality", "средняя")),
                "actions": [str(a) for a in actions_raw],
                "eco_note": str(parsed.get("eco_note", "")),
                "traffic_note": str(parsed.get("traffic_note", "")),
            }
            if not executive["actions"]:
                executive = _fallback_executive(snapshot, incidents)
                source = "mock"
        else:
            executive = _fallback_executive(snapshot, incidents)
            source = "mock"
    else:
        executive = _fallback_executive(snapshot, incidents)
        source = "mock"

    return {
        "source": source,
        "model": getattr(settings, "OLLAMA_MODEL", "qwen2.5:3b"),
        "snapshot": snapshot,
        "incidents": incidents,
        "executive": executive,
    }
