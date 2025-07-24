import random

def calculate_typing_delay(text: str) -> float:
    base_speed = 10  # знаков в секунду
    
    # Базовое время набора
    base_time = len(text) / base_speed
    
    # Добавляем паузы между предложениями
    sentence_count = text.count('.') + text.count('!') + text.count('?')
    sentence_pauses = sentence_count * random.uniform(0.3, 1.2)
    
    # Паузы для запятых
    comma_pauses = text.count(',') * random.uniform(0.1, 0.3)
    
    # Случайный коэффициент скорости
    speed_variation = random.uniform(0.7, 1.3)
    
    # Итоговый расчет
    total_delay = (base_time + sentence_pauses + comma_pauses) * speed_variation
    total_delay = max(1.5, min(8, total_delay)) 
    
    return round(total_delay, 1)