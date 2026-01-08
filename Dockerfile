# Используем python:3.11-slim для минимального размера образа
# Slim образ содержит только необходимые компоненты Python без лишних инструментов
# Это уменьшает размер образа и время сборки, при этом сохраняя все нужные функции
FROM python:3.11-slim

# Установка ffmpeg через apt-get
# Это допустимо по требованиям проекта, так как ffmpeg - системная зависимость
# и не является ML-моделью или интернет-сервисом
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование файлов проекта
COPY . .

# Установка entrypoint
# Запускаем main.py при старте контейнера
ENTRYPOINT ["python", "main.py"]
