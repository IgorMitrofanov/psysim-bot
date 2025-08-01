# Используем официальный образ Python
FROM python:3.12-slim

# Обновляем и устанавливаем ffmpeg + зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы
COPY . .

EXPOSE 55055

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1
ENV BOT_TOKEN=${BOT_TOKEN}
ENV AI_API_KEY=${AI_API_KEY}
ENV DEFAULT_MODEL=${DEFAULT_MODEL}
ENV SESSION_LENGTH_MINUTES=${SESSION_LENGTH_MINUTES}
ENV WARNING_BEFORE_END_MINUTES=${WARNING_BEFORE_END_MINUTES}
ENV LOG_LEVEL=${LOG_LEVEL}
ENV DATABASE_URL=${DATABASE_URL}

# Команда для запуска бота
CMD ["python", "main.py"]