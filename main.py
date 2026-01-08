"""
Точка входа CLI приложения Voice Cleaner.

Обрабатывает аргументы командной строки, сканирует входную директорию
и запускает пайплайн обработки для каждого видеофайла.
"""
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

from pipeline.probe import get_streams_info, NoAudioStreamError, InvalidMediaFileError
from pipeline.analysis import analyze_audio
from pipeline.filters import build_audio_filter
from pipeline.process import process_video
from config import get_preset
from pipeline.ffmpeg import FFmpegError
from env_config import load_env_file, get_env, ENV_LOG_LEVEL, ENV_DEFAULT_PRESET

# Загружаем переменные окружения из .env файла (если есть)
load_env_file()

# Настройка логирования с учётом переменной окружения
log_level_str = get_env(ENV_LOG_LEVEL, 'INFO').upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    """Основная функция CLI."""
    parser = argparse.ArgumentParser(
        description='Voice Cleaner - улучшение разборчивости речи в видеофайлах'
    )
    
    # Значения по умолчанию могут быть переопределены через переменные окружения
    default_input = get_env('INPUT_DIR', 'fixtures')
    default_output = get_env('OUTPUT_DIR', 'output')
    default_preset = get_env(ENV_DEFAULT_PRESET, 'default')
    
    parser.add_argument(
        '--input',
        type=str,
        default=default_input,
        help=f'Путь к директории с входными видеофайлами (по умолчанию: {default_input}, можно задать через INPUT_DIR)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=default_output,
        help=f'Путь к директории для сохранения обработанных файлов (по умолчанию: {default_output}, можно задать через OUTPUT_DIR)'
    )
    
    parser.add_argument(
        '--preset',
        type=str,
        default=default_preset,
        help=f'Пресет обработки: light, default, aggressive, max_voice (по умолчанию: {default_preset}, можно задать через DEFAULT_PRESET)'
    )
    
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Включить подробное логирование (DEBUG уровень)'
    )
    
    args = parser.parse_args()
    
    # Устанавливаем уровень логирования
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Преобразуем пути в Path объекты
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    
    # Валидация входной директории
    if not input_dir.exists():
        logger.error(f"Входная директория не существует: {input_dir}")
        sys.exit(1)
    
    if not input_dir.is_dir():
        logger.error(f"Указанный путь не является директорией: {input_dir}")
        sys.exit(1)
    
    # Создаём выходную директорию, если не существует
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Выходная директория: {output_dir}")
    
    # Загружаем пресет
    try:
        preset = get_preset(args.preset)
        logger.info(f"Используется пресет: {args.preset} - {preset.get('description', '')}")
    except ValueError as e:
        logger.error(f"Ошибка загрузки пресета: {e}")
        sys.exit(1)
    
    # Сканируем входную директорию на наличие видеофайлов
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.webm', '.m4v'}
    video_files = [
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in video_extensions
    ]
    
    if not video_files:
        logger.warning(f"Не найдено видеофайлов в директории: {input_dir}")
        sys.exit(0)
    
    logger.info(f"Найдено видеофайлов: {len(video_files)}")
    
    # Обрабатываем каждый файл
    processed_count = 0
    failed_count = 0
    
    for video_file in video_files:
        logger.info(f"\n{'='*60}")
        logger.info(f"Обработка файла: {video_file.name}")
        logger.info(f"{'='*60}")
        
        try:
            # Шаг 1: Извлечение метаданных
            logger.info("Шаг 1: Извлечение метаданных...")
            probe_info = get_streams_info(str(video_file))
            logger.debug(f"Метаданные: {probe_info}")
            
            # Шаг 2: Анализ аудио
            logger.info("Шаг 2: Анализ аудио...")
            analysis = analyze_audio(str(video_file), probe_info)
            logger.debug(f"Результаты анализа: {analysis}")
            
            # Шаг 3: Построение цепочки фильтров
            logger.info("Шаг 3: Построение цепочки фильтров...")
            filter_chain = build_audio_filter(analysis, preset)
            logger.debug(f"Цепочка фильтров: {filter_chain}")
            
            # Шаг 4: Обработка видео
            logger.info("Шаг 4: Применение фильтров...")
            # Добавляем пресет и timestamp к имени файла для различения версий
            # Формат: original_name_[preset]_YYYY-MM-DD_HH-MM-SS.ext
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            preset_name = args.preset
            file_stem = video_file.stem
            file_suffix = video_file.suffix
            output_filename = f"{file_stem}_{preset_name}_{timestamp}{file_suffix}"
            output_file = output_dir / output_filename
            process_video(str(video_file), str(output_file), filter_chain)
            
            logger.info(f"✓ Успешно обработан: {video_file.name}")
            processed_count += 1
            
        except FileNotFoundError as e:
            logger.error(f"✗ Файл не найден: {e}")
            failed_count += 1
        except NoAudioStreamError as e:
            logger.error(f"✗ Файл не содержит аудио потока: {e}")
            logger.warning(f"  Пропускаем файл: {video_file.name}")
            failed_count += 1
        except InvalidMediaFileError as e:
            logger.error(f"✗ Невалидный или повреждённый файл: {e}")
            failed_count += 1
        except ValueError as e:
            logger.error(f"✗ Ошибка валидации: {e}")
            failed_count += 1
        except FFmpegError as e:
            logger.error(f"✗ Ошибка ffmpeg: {e}")
            logger.debug("  Проверьте, что ffmpeg установлен и файл не повреждён")
            failed_count += 1
        except Exception as e:
            logger.error(f"✗ Неожиданная ошибка при обработке {video_file.name}: {e}", exc_info=True)
            failed_count += 1
    
    # Итоговая статистика
    logger.info(f"\n{'='*60}")
    logger.info(f"Обработка завершена")
    logger.info(f"Успешно обработано: {processed_count}")
    logger.info(f"Ошибок: {failed_count}")
    logger.info(f"{'='*60}")
    
    # Возвращаем код выхода: 0 при успехе, 1 при ошибках
    if failed_count > 0:
        sys.exit(1)
    elif processed_count == 0:
        logger.warning("Не было обработано ни одного файла")
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
