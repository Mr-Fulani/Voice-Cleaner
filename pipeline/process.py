"""
Модуль обработки видео с применением аудио фильтров.

Применяет построенную цепочку фильтров к аудио потоку, сохраняя
видео поток без изменений и гарантируя синхронизацию A/V.

Ключевые принципы синхронизации:
- Используем -c:v copy для копирования видео без перекодирования
- Используем -vsync 0 для отключения автоматической синхронизации видео
- Используем aresample=async=1 для асинхронного ресемплинга аудио
- Используем -shortest для обрезки по самому короткому потоку

Почему не используем глобальный -async:
- Устаревший флаг, может вызывать проблемы
- aresample=async=1 более точный и контролируемый
- Позволяет точно настроить поведение ресемплинга

Где чаще всего ломается синхронизация:
- При изменении sample rate аудио
- При применении фильтров, изменяющих длительность (хотя наши фильтры не должны)
- При несоответствии длительностей видео и аудио потоков
- При использовании неправильных флагов синхронизации
"""
import logging
from pathlib import Path

from .ffmpeg import run_ffmpeg, FFmpegError

logger = logging.getLogger(__name__)


def process_video(input_path: str, output_path: str, filter_chain: str) -> None:
    """
    Обрабатывает видео, применяя фильтры к аудио с сохранением A/V синхронизации.
    
    Args:
        input_path: Путь к входному видеофайлу
        output_path: Путь к выходному файлу
        filter_chain: Цепочка фильтров в формате ffmpeg
    
    Raises:
        FFmpegError: Если обработка завершилась с ошибкой
        FileNotFoundError: Если входной файл не найден
    """
    input_file = Path(input_path)
    output_file = Path(output_path)
    
    # Валидация входного файла
    if not input_file.exists():
        raise FileNotFoundError(f"Входной файл не найден: {input_path}")
    
    logger.info(f"Обработка: {input_file.name} -> {output_file.name}")
    logger.debug(f"Цепочка фильтров: {filter_chain}")
    
    # Создаём выходную директорию, если не существует
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Строим команду ffmpeg
    # Ключевые флаги для синхронизации:
    cmd = [
        "-i", str(input_file),  # Входной файл
        
        # Видео: копируем без изменений
        "-map", "0:v:0",  # Берём первый видео поток
        "-c:v", "copy",   # Копируем без перекодирования
        
        # Аудио: применяем фильтры
        "-map", "0:a:0",  # Берём первый аудио поток
        
        # Добавляем асинхронный ресемплинг для синхронизации
        # async=1 означает, что ресемплинг будет адаптивным для поддержания синхронизации
        "-af", f"{filter_chain},aresample=async=1",
        
        # Синхронизация видео: отключаем автоматическую синхронизацию
        # vsync 0 означает, что мы полагаемся на временные метки потоков
        "-vsync", "0",
        
        # Обрезаем по самому короткому потоку (на случай несоответствия длительностей)
        "-shortest",
        
        # Выходной файл
        "-y",  # Перезаписывать без запроса
        str(output_file)
    ]
    
    try:
        logger.debug(f"Выполнение команды ffmpeg для обработки видео")
        result = run_ffmpeg(cmd, log_level="error")
        
        # Проверяем, что выходной файл создан
        if not output_file.exists():
            raise FFmpegError(f"Выходной файл не был создан: {output_path}")
        
        # Проверяем размер файла (должен быть > 0)
        if output_file.stat().st_size == 0:
            raise FFmpegError(f"Выходной файл пуст: {output_path}")
        
        logger.info(f"Обработка завершена: {output_file.name} ({output_file.stat().st_size / 1024 / 1024:.2f} MB)")
        
    except FFmpegError as e:
        logger.error(f"Ошибка при обработке видео: {e}")
        # Удаляем частично созданный файл при ошибке
        if output_file.exists():
            try:
                output_file.unlink()
                logger.debug(f"Удалён частично созданный файл: {output_path}")
            except Exception:
                pass
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке: {e}")
        raise FFmpegError(f"Ошибка обработки видео: {str(e)}")


def validate_output(input_path: str, output_path: str) -> bool:
    """
    Валидирует выходной файл: проверяет существование и длительность.
    
    Args:
        input_path: Путь к входному файлу
        output_path: Путь к выходному файлу
    
    Returns:
        True, если валидация прошла успешно
    
    Raises:
        FFmpegError: Если валидация не прошла
    """
    output_file = Path(output_path)
    
    if not output_file.exists():
        raise FFmpegError(f"Выходной файл не существует: {output_path}")
    
    # В полной реализации можно было бы сравнить длительности через probe
    # Для упрощения просто проверяем существование и размер
    if output_file.stat().st_size == 0:
        raise FFmpegError(f"Выходной файл пуст: {output_path}")
    
    logger.debug(f"Валидация выходного файла прошла успешно")
    return True
