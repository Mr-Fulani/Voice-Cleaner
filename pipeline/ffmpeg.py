"""
Обёртка для выполнения команд ffmpeg и ffprobe.

Предоставляет единый интерфейс для запуска команд с обработкой ошибок
и логированием.
"""
import subprocess
import logging
import json
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _get_ffmpeg_path() -> str:
    """Получает путь к ffmpeg из переменной окружения или использует 'ffmpeg'."""
    return os.getenv('FFMPEG_PATH', 'ffmpeg')


def _get_ffprobe_path() -> str:
    """Получает путь к ffprobe из переменной окружения или использует 'ffprobe'."""
    return os.getenv('FFPROBE_PATH', 'ffprobe')


class FFmpegError(Exception):
    """Исключение для ошибок выполнения ffmpeg/ffprobe."""
    pass


def run_ffmpeg(cmd: list[str], log_level: str = "error") -> subprocess.CompletedProcess:
    """
    Выполняет команду ffmpeg.
    
    Args:
        cmd: Список аргументов команды (первый элемент - 'ffmpeg')
        log_level: Уровень логирования ffmpeg (error, warning, info, debug)
    
    Returns:
        CompletedProcess объект с результатами выполнения
    
    Raises:
        FFmpegError: Если выполнение завершилось с ошибкой
    """
    # Добавляем уровень логирования в команду
    # Используем subprocess без shell для безопасности и контроля
    ffmpeg_path = _get_ffmpeg_path()
    full_cmd = [ffmpeg_path, "-loglevel", log_level] + cmd
    
    logger.debug(f"Выполнение команды: {' '.join(full_cmd)}")
    
    try:
        # Запускаем процесс и перехватываем stderr для анализа ошибок
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            check=False  # Не выбрасываем исключение автоматически, обрабатываем сами
        )
        
        if result.returncode != 0:
            # Парсим stderr для поиска релевантной информации об ошибке
            error_msg = _parse_ffmpeg_error(result.stderr)
            logger.error(f"Ошибка ffmpeg: {error_msg}")
            raise FFmpegError(f"Команда ffmpeg завершилась с ошибкой: {error_msg}")
        
        # Логируем stderr даже при успехе, так как там может быть полезная информация
        if result.stderr:
            logger.debug(f"stderr ffmpeg: {result.stderr}")
        
        return result
        
    except FileNotFoundError:
        ffmpeg_path = _get_ffmpeg_path()
        raise FFmpegError(
            f"ffmpeg не найден по пути '{ffmpeg_path}'. "
            "Убедитесь, что ffmpeg установлен и доступен в PATH, "
            "или установите переменную окружения FFMPEG_PATH"
        )
    except subprocess.TimeoutExpired:
        raise FFmpegError("Команда ffmpeg превысила время ожидания")
    except Exception as e:
        raise FFmpegError(f"Неожиданная ошибка при выполнении ffmpeg: {str(e)}")


def run_ffprobe(cmd: list[str]) -> dict:
    """
    Выполняет команду ffprobe и возвращает результат в виде словаря.
    
    Args:
        cmd: Список аргументов команды (без 'ffprobe' в начале)
    
    Returns:
        Словарь с результатами выполнения ffprobe (обычно JSON)
    
    Raises:
        FFmpegError: Если выполнение завершилось с ошибкой или результат невалиден
    """
    # ffprobe всегда используем с JSON выводом для структурированных данных
    ffprobe_path = _get_ffprobe_path()
    full_cmd = [ffprobe_path, "-v", "error", "-print_format", "json", "-show_format", "-show_streams"] + cmd
    
    logger.debug(f"Выполнение команды: {' '.join(full_cmd)}")
    
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            error_msg = _parse_ffmpeg_error(result.stderr)
            logger.error(f"Ошибка ffprobe: {error_msg}")
            raise FFmpegError(f"Команда ffprobe завершилась с ошибкой: {error_msg}")
        
        # Парсим JSON результат
        try:
            data = json.loads(result.stdout)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Не удалось распарсить JSON от ffprobe: {result.stdout}")
            raise FFmpegError(f"Невалидный JSON от ffprobe: {str(e)}")
        
    except FileNotFoundError:
        ffprobe_path = _get_ffprobe_path()
        raise FFmpegError(
            f"ffprobe не найден по пути '{ffprobe_path}'. "
            "Убедитесь, что ffprobe установлен и доступен в PATH, "
            "или установите переменную окружения FFPROBE_PATH"
        )
    except subprocess.TimeoutExpired:
        raise FFmpegError("Команда ffprobe превысила время ожидания")
    except Exception as e:
        raise FFmpegError(f"Неожиданная ошибка при выполнении ffprobe: {str(e)}")


def _parse_ffmpeg_error(stderr: str) -> str:
    """
    Парсит stderr от ffmpeg/ffprobe для извлечения понятного сообщения об ошибке.
    
    Args:
        stderr: Текст stderr от процесса
    
    Returns:
        Понятное сообщение об ошибке
    """
    if not stderr:
        return "Неизвестная ошибка (stderr пуст)"
    
    lines = stderr.strip().split('\n')
    
    # Ищем строки с ошибками (обычно содержат "Error", "Invalid", "No such file")
    error_lines = [
        line for line in lines
        if any(keyword in line.lower() for keyword in ['error', 'invalid', 'no such file', 'cannot', 'failed'])
    ]
    
    if error_lines:
        # Возвращаем последнюю строку с ошибкой (обычно самая релевантная)
        return error_lines[-1].strip()
    
    # Если не нашли явных ошибок, возвращаем последние строки stderr
    return lines[-1].strip() if lines else "Неизвестная ошибка"
