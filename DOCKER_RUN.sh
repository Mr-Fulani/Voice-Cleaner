#!/bin/bash
# Скрипт для запуска Voice Cleaner в Docker

# Сборка образа (если ещё не собран)
echo "Сборка Docker образа..."
docker build -t voice-cleaner .

# Запуск обработки
echo "Запуск обработки с пресетом max_voice..."
docker run --rm \
  -v $(pwd)/fixtures:/app/fixtures \
  -v $(pwd)/output:/app/output \
  voice-cleaner \
  --input /app/fixtures \
  --output /app/output \
  --preset max_voice

echo "Обработка завершена! Результаты в директории output/"
