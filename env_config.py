"""
Модуль для работы с переменными окружения.

Использует только стандартную библиотеку Python (os.getenv).
Не требует внешних зависимостей типа python-dotenv.
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def load_env_file(env_path: Optional[str] = None) -> None:
    """
    Загружает переменные из .env файла в окружение.
    
    Использует только стандартную библиотеку Python.
    Формат файла: KEY=value (по одной переменной на строку)
    
    Args:
        env_path: Путь к .env файлу. Если None, ищет .env в текущей директории.
    """
    if env_path is None:
        env_path = Path.cwd() / '.env'
    else:
        env_path = Path(env_path)
    
    if not env_path.exists():
        logger.debug(f"Файл .env не найден: {env_path}, используем переменные окружения системы")
        return
    
    logger.debug(f"Загрузка переменных из .env: {env_path}")
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Пропускаем пустые строки и комментарии
                if not line or line.startswith('#'):
                    continue
                
                # Парсим KEY=value
                if '=' not in line:
                    logger.warning(f"Строка {line_num} в .env пропущена (нет '='): {line}")
                    continue
                
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Убираем кавычки, если есть
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                # Устанавливаем переменную окружения только если её ещё нет
                # (системные переменные имеют приоритет)
                if key and key not in os.environ:
                    os.environ[key] = value
                    logger.debug(f"Загружена переменная: {key}")
        
        logger.info(f"Переменные из .env загружены успешно")
        
    except Exception as e:
        logger.warning(f"Ошибка при загрузке .env файла: {e}, используем системные переменные")


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Получает значение переменной окружения.
    
    Args:
        key: Имя переменной
        default: Значение по умолчанию, если переменная не установлена
    
    Returns:
        Значение переменной или default
    """
    return os.getenv(key, default)


def get_env_bool(key: str, default: bool = False) -> bool:
    """
    Получает булево значение переменной окружения.
    
    Args:
        key: Имя переменной
        default: Значение по умолчанию
    
    Returns:
        True если значение 'true', '1', 'yes', 'on' (case-insensitive)
    """
    value = get_env(key)
    if value is None:
        return default
    
    return value.lower() in ('true', '1', 'yes', 'on')


def get_env_int(key: str, default: Optional[int] = None) -> Optional[int]:
    """
    Получает целочисленное значение переменной окружения.
    
    Args:
        key: Имя переменной
        default: Значение по умолчанию
    
    Returns:
        Целое число или default
    """
    value = get_env(key)
    if value is None:
        return default
    
    try:
        return int(value)
    except ValueError:
        logger.warning(f"Не удалось преобразовать {key}={value} в int, используется default={default}")
        return default


# Константы для имён переменных окружения
ENV_LOG_LEVEL = 'LOG_LEVEL'
ENV_INPUT_DIR = 'INPUT_DIR'
ENV_OUTPUT_DIR = 'OUTPUT_DIR'
ENV_DEFAULT_PRESET = 'DEFAULT_PRESET'
ENV_FFMPEG_PATH = 'FFMPEG_PATH'
ENV_FFPROBE_PATH = 'FFPROBE_PATH'
ENV_FFMPEG_TIMEOUT = 'FFMPEG_TIMEOUT'
ENV_MAX_OUTPUT_SIZE_MB = 'MAX_OUTPUT_SIZE_MB'
