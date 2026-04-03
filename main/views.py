from django.shortcuts import render
from .models import CityMetric

def home(request):
    # Забираем все метрики из базы данных
    metrics = CityMetric.objects.all()
    
    # Создаем словарь для удобного доступа в шаблоне
    metrics_dict = {m.name.lower(): m for m in metrics}
    
    context = {
        'metrics': metrics_dict,
        'project_name': 'EcoTransit Almaty',
    }
    return render(request, 'message.html', context)