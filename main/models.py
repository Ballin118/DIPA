from django.db import models

class CityMetric(models.Model):
    name = models.CharField(max_length=100)  # Название (например, "CO2")
    value = models.FloatField()               # Значение (например, 420.5)
    unit = models.CharField(max_length=20)    # Единица измерения (ppm, км/ч)
    timestamp = models.DateTimeField(auto_now_add=True) # Время записи

    def __str__(self):
        return f"{self.name}: {self.value} {self.unit}"
