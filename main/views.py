from django.shortcuts import render

def home(request):
    # Наши заглушки
    mock_data = {
        'title': 'DIPA Проект',
        'description': 'Работаем с мок-данными',
        'items': ['Анализ GRP', 'Экология', 'Транспорт']
    }
    return render(request, 'message.html', mock_data)