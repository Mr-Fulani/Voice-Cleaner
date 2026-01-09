"""
Модуль построения адаптивных цепочек аудио фильтров.

На основе результатов анализа аудио строит оптимальную цепочку фильтров
для улучшения разборчивости речи. Порядок фильтров критически важен
для качества результата.

Порядок фильтров (важно!):
1. highpass/lowpass - убираем ненужные частоты ДО обработки
2. afftdn (шумоподавление) - убираем шум ДО компрессии
3. acompressor - выравниваем динамику
4. firequalizer - частотная коррекция ПОСЛЕ компрессии
5. alimiter - финальное ограничение пиков

Почему такой порядок:
- Фильтрация частот до шумоподавления уменьшает артефакты
- Шумоподавление до компрессии предотвращает усиление шума
- Компрессия выравнивает уровни перед эквалайзером
- Эквалайзер после компрессии работает с выровненным сигналом
- Лимитер в конце предотвращает клиппинг

Артефакты, которые могут появиться:
- Металлический звук от агрессивного шумоподавления
- Дыхание/пумпинг от компрессии
- Искажения от эквалайзера на высоких уровнях
- Клиппинг при неправильной настройке лимитера

Почему не используем neural filters:
- Требуют ML-модели (запрещено по требованиям)
- Требуют интернет-доступ для загрузки моделей
- Медленнее работают
- Наш подход использует только DSP (Digital Signal Processing)
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def build_audio_filter(analysis: dict, preset: dict) -> str:
    """
    Строит адаптивную цепочку аудио фильтров на основе анализа и пресета.
    
    Args:
        analysis: Результат analyze_audio() с информацией об аудио
        preset: Параметры пресета из config.py
    
    Returns:
        Строка с цепочкой фильтров для ffmpeg (формат: filter1,filter2,filter3)
    """
    logger.debug("Построение цепочки фильтров")
    
    filters = []
    
    # 1. Highpass фильтр - убираем инфранизкие частоты (музыка, басы)
    # Эти частоты не несут речевую информацию и могут создавать артефакты
    # Более агрессивная фильтрация помогает убрать фоновую музыку
    highpass_freq = preset.get('highpass_freq', 80)
    # Используем стандартный highpass (order по умолчанию)
    filters.append(f"highpass=f={highpass_freq}")
    logger.debug(f"Добавлен highpass: {highpass_freq} Hz")
    
    # 2. Lowpass фильтр - убираем очень высокие частоты (шипение, шумы)
    # Уменьшает шум и артефакты, фокус на речевом диапазоне (300-3400 Hz)
    # Более узкая полоса помогает убрать фоновые шумы
    lowpass_freq = preset.get('lowpass_freq', 8000)
    # Используем стандартный lowpass
    filters.append(f"lowpass=f={lowpass_freq}")
    logger.debug(f"Добавлен lowpass: {lowpass_freq} Hz")
    
    # 3. Шумоподавление (afftdn) - убираем фоновый шум, гул, шипение
    # Адаптируем агрессивность на основе уровня шума
    noise_reduction = preset.get('noise_reduction', {})
    nr = _adapt_noise_reduction(
        noise_reduction.get('nr', 12),
        analysis.get('noise_level_db', -45)
    )
    nt = noise_reduction.get('nt', 'w')
    # Используем максимальное шумоподавление
    filters.append(f"afftdn=nr={nr}:nt={nt}")
    logger.debug(f"Добавлен afftdn: nr={nr}, nt={nt} (максимальное подавление)")
    
    # 4. Компрессор (acompressor) - выравниваем динамику
    # Делает тихую речь громче, громкую - тише
    compressor = preset.get('compressor', {})
    threshold = compressor.get('threshold', -20)
    ratio = compressor.get('ratio', 3)
    attack = compressor.get('attack', 20)
    release = compressor.get('release', 200)
    filters.append(
        f"acompressor=threshold={threshold}dB:ratio={ratio}:"
        f"attack={attack}:release={release}"
    )
    logger.debug(f"Добавлен acompressor: threshold={threshold}dB, ratio={ratio}")
    
    # 5. Эквалайзер (firequalizer) - частотная коррекция
    # Усиливаем речевые частоты (300-3000 Hz), убираем лишнее
    # Критически важно для подавления музыки и усиления речи
    equalizer = preset.get('equalizer', {})
    eq_entries = equalizer.get('entries', [])
    if eq_entries:
        eq_string = _build_equalizer_string(eq_entries)
        filters.append(f"firequalizer=gain_entry='{eq_string}'")
        logger.debug(f"Добавлен firequalizer с {len(eq_entries)} точками")

        # Дополнительное усиление речевых характеристик
        if preset.get('voice_enhancement', False):
            # Усиление согласных (3000 Hz) и звонких звуков (1000 Hz)
            filters.append("equalizer=f=3000:width_type=o:width=1:g=2")
            filters.append("equalizer=f=1000:width_type=o:width=1:g=1")
            # Дополнительное усиление для четкости
            filters.append("equalizer=f=4000:width_type=o:width=0.5:g=1")
            logger.debug("Добавлено дополнительное усиление речевых характеристик")

        # Дополнительные фильтры для ultra_clean
        if preset.get('center_extraction', False) and preset.get('harmonic_analysis', False):
            # Комбинированная обработка: центр + гармоники
            # Добавляем еще один проход эквализации после извлечения центра
            filters.append("equalizer=f=800:width_type=o:width=1:g=2")
            filters.append("equalizer=f=2500:width_type=o:width=1:g=3")
            logger.debug("Добавлена комбинированная обработка центр+гармоники")
    
    # 6. Лимитер (alimiter) - финальное ограничение пиков
    # Предотвращает клиппинг и перегрузку
    limiter = preset.get('limiter', {})
    limit = limiter.get('limit', 0.95)
    filters.append(f"alimiter=limit={limit}")
    logger.debug(f"Добавлен alimiter: limit={limit}")
    
    # 7. Дополнительное подавление музыки через multiple highpass фильтры
    # Множественные highpass помогают максимально агрессивно убрать низкие частоты музыки
    noise_gate = preset.get('noise_gate_threshold', -35)
    if noise_gate > -30:  # Если используется агрессивный режим
        # Добавляем второй, третий и четвертый highpass для максимального подавления
        second_highpass = min(highpass_freq + 40, 290)
        third_highpass = min(highpass_freq + 80, 330)
        fourth_highpass = min(highpass_freq + 120, 370)
        filters.append(f"highpass=f={second_highpass}")
        filters.append(f"highpass=f={third_highpass}")
        filters.append(f"highpass=f={fourth_highpass}")
        logger.debug(f"Добавлены дополнительные highpass: {second_highpass}, {third_highpass}, {fourth_highpass} Hz для экстремального подавления басов")
    
    # 8. Нормализация громкости - компенсируем снижение от фильтров
    # Фильтры (особенно highpass/lowpass и компрессор) могут снизить общий уровень
    # Добавляем усиление для компенсации, но не слишком агрессивно
    # Адаптируем на основе разницы между речью и шумом
    level_diff = analysis.get('speech_level_db', -18) - analysis.get('noise_level_db', -45)
    if level_diff > 20:
        # Хорошее соотношение сигнал/шум - умеренное усиление
        gain_db = 5.0
    else:
        # Плохое соотношение - большее усиление для компенсации
        gain_db = 8.0

    # Для max_voice пресета добавляем максимальное усиление речи
    if noise_gate > -30:
        gain_db += 3.0  # Дополнительные +3dB для голоса
    
    filters.append(f"volume={gain_db}dB")
    logger.debug(f"Добавлена нормализация громкости: +{gain_db}dB")
    
    # Объединяем все фильтры через запятую
    filter_chain = ",".join(filters)
    
    logger.info(f"Построена цепочка фильтров: {len(filters)} фильтров")
    logger.debug(f"Полная цепочка: {filter_chain}")
    
    return filter_chain


def _adapt_noise_reduction(base_nr: float, noise_level_db: float) -> float:
    """
    Адаптирует уровень шумоподавления на основе фактического уровня шума.
    
    Args:
        base_nr: Базовое значение шумоподавления из пресета
        noise_level_db: Фактический уровень шума в dB
    
    Returns:
        Адаптированное значение шумоподавления
    """
    # Если шум очень тихий (< -50 dB), уменьшаем шумоподавление
    # Если шум громкий (> -35 dB), увеличиваем
    if noise_level_db < -50:
        return max(3, base_nr * 0.7)  # Уменьшаем на 30%, но не меньше 3
    elif noise_level_db > -35:
        return min(24, base_nr * 1.3)  # Увеличиваем на 30%, но не больше 24
    
    return base_nr


def _build_equalizer_string(entries: list) -> str:
    """
    Строит строку gain_entry для firequalizer.
    
    Args:
        entries: Список кортежей (частота, усиление в dB)
    
    Returns:
        Строка в формате: entry(100,0);entry(300,4);...
    """
    eq_parts = [f"entry({freq},{gain})" for freq, gain in entries]
    return ";".join(eq_parts)
