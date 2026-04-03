# DIPA — Smart City Management Dashboard (MVP)

Веб-панель для мониторинга состояния города (на примере **Алматы**): транспорт, экология, сигналы по правилам и **текстовый слой** с выводами и рекомендациями (локальная LLM + резервный mock).

## Возможности

- **Карта** — Яндекс.Карты JS API 2.1: слой пробок, геолокация, две метки (центр мониторинга и зона внимания).
- **Индекс пробок** — расчёт от метрик и времени суток (Asia/Almaty), «живой» график и API.
- **KPI** — CO₂, средняя скорость, шум (из БД или значения по умолчанию).
- **Инциденты** — правила отклонений с приоритетом (high / medium / low).
- **AI** — запрос к **Ollama** (`qwen2.5:3b`): сводка, критичность, шаги, заметки по экологии и транспорту; при недоступности Ollama — готовый текст из логики на Python.

## Стек

| Компонент | Технология |
|-----------|------------|
| Backend | Python 3, **Django** |
| БД | **SQLite** (dev), модель `CityMetric` |
| HTTP-клиент к LLM | **httpx** |
| Локальная LLM | **Ollama** + **Qwen 2.5 3B** |
| Карты | **Яндекс.Карты** API 2.1 |
| Графики | **Chart.js** (CDN) |

## Быстрый старт

### 1. Клонирование и виртуальное окружение

```bash
cd DIPA
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Переменные окружения

Скопируйте `env.example` в `.env` и заполните как минимум:

```bash
cp env.example .env
```

| Переменная | Назначение |
|------------|------------|
| `YANDEX_MAPS_API_KEY` | Ключ [JavaScript API и HTTP Геокодер](https://developer.tech.yandex.ru/) — без него карта не загрузится (покажется подсказка). |
| `DJANGO_SECRET_KEY` | Секрет Django для production (опционально в dev). |
| `OLLAMA_BASE_URL` | По умолчанию `http://127.0.0.1:11434`. |
| `OLLAMA_MODEL` | По умолчанию `qwen2.5:3b`. |

Опционально: `MAP_CENTER_LAT`, `MAP_CENTER_LON`, `MAP_DEFAULT_ZOOM`, `MAP_HOTSPOT_*` — центр и вторая метка на карте.

### 3. Ollama (локальная модель)

```bash
ollama pull qwen2.5:3b
ollama serve   # если сервис ещё не запущен
```

### 4. Миграции и сервер

```bash
python manage.py migrate
python manage.py runserver
```

Откройте в браузере: **http://127.0.0.1:8000/**

## API

| Метод | Путь | Описание |
|--------|------|----------|
| GET | `/api/traffic/live/` | Текущий индекс пробок, история точек, уровень, `local_hour`, `time_scale`. |
| GET | `/api/insights/` | Снимок города, инциденты, executive-текст (LLM или mock). |

## Структура проекта

```
DIPA/
├── core/           # настройки Django, urls
├── main/
│   ├── ai_service.py   # снимок, правила, Ollama, live traffic
│   ├── models.py       # CityMetric
│   ├── views.py
│   └── templates/index.html
├── manage.py
├── requirements.txt
└── env.example
```

## Логика (кратко для защиты)

1. **Метрики** подмешиваются из SQLite (`CityMetric`: имена `co2`, `speed`, `noise`) или берутся дефолты.
2. **Индекс пробок** — эвристика от скорости и шума, затем **множитель по часу** (Алматы), плюс «живые» колебания для графика.
3. **Инциденты** — детерминированные правила по порогам из снимка.
4. **Текст для руководства** — промпт к Qwen с JSON-ответом; при ошибке сети/парсинга — fallback-текст.

## Лицензия и карты

Использование Яндекс.Карт регулируется [условиями сервиса](https://yandex.ru/legal/maps_termsofuse/). Ключ API не публикуйте в открытом репозитории.

## Авторы

Проект подготовлен в рамках хакатона / учебного кейса **Smart City Management Dashboard**.
