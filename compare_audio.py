#!/usr/bin/env python3
"""
Скрипт для сравнения аудио характеристик оригинального и обработанного файлов.
Помогает увидеть различия в обработке.
"""
import subprocess
import sys
from pathlib import Path


def get_audio_info(file_path: str) -> dict:
    """Получает информацию об аудио через ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a:0",
        file_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    
    import json
    data = json.loads(result.stdout)
    if data.get('streams'):
        return data['streams'][0]
    return {}


def get_volume_stats(file_path: str) -> dict:
    """Получает статистику громкости через volumedetect."""
    cmd = [
        "ffmpeg", "-i", file_path,
        "-af", "volumedetect",
        "-f", "null", "-"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    stats = {}
    for line in result.stderr.split('\n'):
        if 'mean_volume:' in line:
            try:
                value = float(line.split('mean_volume:')[1].split('dB')[0].strip())
                stats['mean_volume'] = value
            except:
                pass
        elif 'max_volume:' in line:
            try:
                value = float(line.split('max_volume:')[1].split('dB')[0].strip())
                stats['max_volume'] = value
            except:
                pass
    
    return stats


def compare_files(original: str, processed: str):
    """Сравнивает два аудио файла."""
    print("=" * 70)
    print("СРАВНЕНИЕ АУДИО ФАЙЛОВ")
    print("=" * 70)
    print(f"\nОригинал: {original}")
    print(f"Обработанный: {processed}\n")
    
    # Метаданные
    orig_info = get_audio_info(original)
    proc_info = get_audio_info(processed)
    
    print("МЕТАДАННЫЕ:")
    print(f"  Кодек: {orig_info.get('codec_name', 'N/A')} → {proc_info.get('codec_name', 'N/A')}")
    print(f"  Sample rate: {orig_info.get('sample_rate', 'N/A')} → {proc_info.get('sample_rate', 'N/A')}")
    print(f"  Каналы: {orig_info.get('channels', 'N/A')} → {proc_info.get('channels', 'N/A')}")
    
    # Громкость
    orig_vol = get_volume_stats(original)
    proc_vol = get_volume_stats(processed)
    
    print("\nГРОМКОСТЬ:")
    if 'mean_volume' in orig_vol and 'mean_volume' in proc_vol:
        diff = proc_vol['mean_volume'] - orig_vol['mean_volume']
        print(f"  Средний уровень: {orig_vol['mean_volume']:.1f} dB → {proc_vol['mean_volume']:.1f} dB (изменение: {diff:+.1f} dB)")
    
    if 'max_volume' in orig_vol and 'max_volume' in proc_vol:
        diff = proc_vol['max_volume'] - orig_vol['max_volume']
        print(f"  Максимальный уровень: {orig_vol['max_volume']:.1f} dB → {proc_vol['max_volume']:.1f} dB (изменение: {diff:+.1f} dB)")
    
    # Размер файлов
    orig_size = Path(original).stat().st_size / (1024 * 1024)
    proc_size = Path(processed).stat().st_size / (1024 * 1024)
    size_diff = proc_size - orig_size
    
    print("\nРАЗМЕР ФАЙЛОВ:")
    print(f"  Оригинал: {orig_size:.2f} MB")
    print(f"  Обработанный: {proc_size:.2f} MB (изменение: {size_diff:+.2f} MB)")
    
    print("\n" + "=" * 70)
    print("РЕКОМЕНДАЦИИ:")
    print("=" * 70)
    
    if abs(diff) < 1.0:
        print("✓ Уровни громкости выровнены хорошо")
    else:
        print(f"⚠ Разница в громкости: {abs(diff):.1f} dB")
    
    print("\nДля более заметных изменений попробуйте:")
    print("  python3 main.py --preset aggressive  # Более агрессивная обработка")
    print("  python3 main.py --preset test        # Тестовый пресет с заметными изменениями")
    print("\nОбратите внимание на:")
    print("  - Разборчивость речи (должна улучшиться)")
    print("  - Фоновый шум (должен уменьшиться)")
    print("  - Общее качество звука")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Использование: python3 compare_audio.py <оригинал> <обработанный>")
        print("\nПример:")
        print("  python3 compare_audio.py fixtures/video.mp4 output/video.mp4")
        sys.exit(1)
    
    original = sys.argv[1]
    processed = sys.argv[2]
    
    if not Path(original).exists():
        print(f"Ошибка: файл не найден: {original}")
        sys.exit(1)
    
    if not Path(processed).exists():
        print(f"Ошибка: файл не найден: {processed}")
        sys.exit(1)
    
    compare_files(original, processed)
