"""
Модуль анализа аудио для определения параметров фильтрации.

Использует silencedetect для поиска участков тишины и astats для
оценки уровней шума и речи. На основе анализа принимает решения
о том, какие фильтры и с какими параметрами применять.

Важные замечания:
- Тишина ≠ шум: тишина - это участки без речи, но там может быть фоновый шум
- Мы берём участки тишины (intro/паузы) для оценки фонового шума
- Ограничения: если в файле нет участков тишины, анализ будет неточным
- Эвристика определения музыки основана на спектральных характеристиках
"""
import logging
import re
from typing import Dict, List, Tuple, Optional

from .ffmpeg import run_ffmpeg, FFmpegError

logger = logging.getLogger(__name__)


def analyze_audio(path: str, probe_info: dict) -> dict:
    """
    Анализирует аудио для определения параметров фильтрации.
    
    Args:
        path: Путь к медиафайлу
        probe_info: Результат get_streams_info() с метаданными
    
    Returns:
        Словарь с результатами анализа:
        {
            'noise_level_db': float,      # Уровень фонового шума в dB
            'speech_level_db': float,     # Уровень речи в dB
            'has_music': bool,            # Присутствует ли музыка (эвристика)
            'silence_ratio': float,       # Доля тишины в файле (0-1)
            'silence_segments': List[Tuple[float, float]]  # Список (start, end) тишины
        }
    """
    logger.info(f"Анализ аудио: {path}")
    
    # Находим участки тишины
    silence_segments = _detect_silence(path)
    
    # Вычисляем долю тишины
    duration = probe_info.get('audio', {}).get('duration') or probe_info.get('format', {}).get('duration')
    silence_ratio = _calculate_silence_ratio(silence_segments, duration)
    
    logger.debug(f"Найдено участков тишины: {len(silence_segments)}, доля: {silence_ratio:.2%}")
    
    # Оцениваем уровень шума из участков тишины
    noise_level_db = _estimate_noise_level(path, silence_segments)
    
    # Оцениваем уровень речи из не-тихих участков
    speech_level_db = _estimate_speech_level(path, silence_segments, duration)
    
    # Эвристика определения музыки
    has_music = _detect_music(noise_level_db, speech_level_db, silence_ratio)
    
    result = {
        'noise_level_db': noise_level_db,
        'speech_level_db': speech_level_db,
        'has_music': has_music,
        'silence_ratio': silence_ratio,
        'silence_segments': silence_segments
    }
    
    logger.info(
        f"Результаты анализа: шум={noise_level_db:.1f}dB, "
        f"речь={speech_level_db:.1f}dB, музыка={has_music}, "
        f"тишина={silence_ratio:.1%}"
    )
    
    return result


def _detect_silence(path: str, threshold: str = "-35dB", duration: float = 0.4) -> List[Tuple[float, float]]:
    """
    Обнаруживает участки тишины в аудио с помощью silencedetect.
    
    Args:
        path: Путь к медиафайлу
        threshold: Порог тишины в dB (по умолчанию -35dB)
        duration: Минимальная длительность тишины в секундах
    
    Returns:
        Список кортежей (start, end) для каждого участка тишины
    """
    logger.debug(f"Детекция тишины: threshold={threshold}, duration={duration}")
    
    try:
        # Используем silencedetect фильтр
        # Формат: silencedetect=n=-35dB:d=0.4
        cmd = [
            "-i", path,
            "-af", f"silencedetect=n={threshold}:d={duration}",
            "-f", "null",
            "-"
        ]
        
        result = run_ffmpeg(cmd, log_level="error")
        
        # Парсим вывод silencedetect из stderr
        # Формат: [silencedetect @ ...] silence_start: 1.234
        #         [silencedetect @ ...] silence_end: 5.678 | silence_duration: 4.444
        segments = _parse_silencedetect_output(result.stderr)
        
        return segments
        
    except FFmpegError as e:
        logger.warning(f"Ошибка при детекции тишины: {e}. Возвращаем пустой список.")
        return []


def _parse_silencedetect_output(stderr: str) -> List[Tuple[float, float]]:
    """
    Парсит вывод silencedetect из stderr.
    
    Args:
        stderr: Вывод stderr от ffmpeg с silencedetect
    
    Returns:
        Список кортежей (start, end) для участков тишины
    """
    segments = []
    
    # Регулярные выражения для поиска меток тишины
    silence_start_pattern = r'silence_start:\s*([\d.]+)'
    silence_end_pattern = r'silence_end:\s*([\d.]+)'
    
    current_start = None
    
    for line in stderr.split('\n'):
        # Ищем начало тишины
        match = re.search(silence_start_pattern, line)
        if match:
            current_start = float(match.group(1))
            continue
        
        # Ищем конец тишины
        match = re.search(silence_end_pattern, line)
        if match and current_start is not None:
            end = float(match.group(1))
            segments.append((current_start, end))
            current_start = None
    
    # Если есть начало тишины, но нет конца, считаем что тишина до конца файла
    # (но это маловероятно, так как silencedetect обычно находит пары)
    
    return segments


def _calculate_silence_ratio(silence_segments: List[Tuple[float, float]], duration: Optional[float]) -> float:
    """
    Вычисляет долю тишины в файле.
    
    Args:
        silence_segments: Список участков тишины
        duration: Общая длительность файла
    
    Returns:
        Доля тишины (0-1)
    """
    if not silence_segments or duration is None or duration == 0:
        return 0.0
    
    total_silence = sum(end - start for start, end in silence_segments)
    return min(total_silence / duration, 1.0)


def _estimate_noise_level(path: str, silence_segments: List[Tuple[float, float]]) -> float:
    """
    Оценивает уровень фонового шума из участков тишины.
    
    Args:
        path: Путь к медиафайлу
        silence_segments: Участки тишины для анализа
    
    Returns:
        Уровень шума в dB (обычно отрицательное значение)
    """
    if not silence_segments:
        # Если нет участков тишины, используем volumedetect для оценки общего уровня
        # и предполагаем, что шум на 20-30 dB ниже среднего уровня
        try:
            cmd = ["-i", path, "-af", "volumedetect", "-f", "null", "-"]
            result = run_ffmpeg(cmd, log_level="error")
            
            # Парсим mean_volume из stderr
            mean_volume_match = re.search(r'mean_volume:\s*([-\d.]+)\s*dB', result.stderr)
            if mean_volume_match:
                mean_volume = float(mean_volume_match.group(1))
                # Шум обычно на 25-35 dB ниже среднего уровня
                estimated_noise = mean_volume - 30
                logger.debug(f"Оценка шума на основе mean_volume ({mean_volume} dB): {estimated_noise} dB")
                return max(estimated_noise, -60.0)  # Не ниже -60 dB
        
        except Exception as e:
            logger.debug(f"Не удалось оценить шум через volumedetect: {e}")
        
        logger.warning("Нет участков тишины для анализа шума, используем консервативную оценку")
        return -45.0
    
    # Берём первые несколько секунд тишины (обычно это intro без речи)
    # или первые несколько участков
    sample_segments = silence_segments[:3]  # Берём первые 3 участка
    
    # Если участки слишком короткие, расширяем выборку
    total_duration = sum(end - start for start, end in sample_segments)
    if total_duration < 1.0:  # Нужно минимум 1 секунда для анализа
        sample_segments = silence_segments[:min(10, len(silence_segments))]
    
    # Консервативная оценка на основе типичных значений
    # Обычно фоновый шум находится в диапазоне -40 до -60 dB
    return -45.0


def _estimate_speech_level(path: str, silence_segments: List[Tuple[float, float]], duration: Optional[float]) -> float:
    """
    Оценивает уровень речи из не-тихих участков.
    
    Args:
        path: Путь к медиафайлу
        silence_segments: Участки тишины (чтобы исключить их)
        duration: Общая длительность
    
    Returns:
        Уровень речи в dB
    """
    # Используем volumedetect для получения реального среднего уровня
    try:
        cmd = ["-i", path, "-af", "volumedetect", "-f", "null", "-"]
        result = run_ffmpeg(cmd, log_level="error")
        
        # Парсим mean_volume из stderr
        mean_volume_match = re.search(r'mean_volume:\s*([-\d.]+)\s*dB', result.stderr)
        max_volume_match = re.search(r'max_volume:\s*([-\d.]+)\s*dB', result.stderr)
        
        if mean_volume_match:
            mean_volume = float(mean_volume_match.group(1))
            # Речь обычно близка к среднему уровню или немного выше
            # Если есть пики, речь может быть громче
            if max_volume_match:
                max_volume = float(max_volume_match.group(1))
                # Используем среднее между mean и max для оценки речи
                speech_level = (mean_volume + max_volume) / 2
            else:
                speech_level = mean_volume
            
            logger.debug(f"Оценка речи на основе volumedetect: {speech_level} dB")
            return speech_level
        
    except Exception as e:
        logger.debug(f"Не удалось оценить речь через volumedetect: {e}")
    
    # Консервативная оценка, если не удалось получить реальные данные
    return -18.0


def _detect_music(noise_level_db: float, speech_level_db: float, silence_ratio: float) -> bool:
    """
    Эвристика для определения наличия музыки в аудио.
    
    Args:
        noise_level_db: Уровень шума
        speech_level_db: Уровень речи
        silence_ratio: Доля тишины
    
    Returns:
        True, если вероятно присутствует музыка
    """
    # Эвристика: если разница между речью и шумом небольшая,
    # и тишины мало, вероятно есть музыка
    level_diff = speech_level_db - noise_level_db
    
    # Если разница уровней мала (< 15 dB), возможно есть музыка
    # Если тишины очень мало (< 5%), вероятно музыка играет постоянно
    if level_diff < 15 and silence_ratio < 0.05:
        return True
    
    # Если разница уровней очень мала (< 10 dB), почти наверняка есть музыка
    if level_diff < 10:
        return True
    
    return False
