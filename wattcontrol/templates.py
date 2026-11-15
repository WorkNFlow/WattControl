"""Детерминированные шаблоны предупреждений системы «ВаттКонтроль».

Подстановка вычисленных физических величин в готовые шаблоны без нейросетей и NLG.
"""

from typing import Union


def format_duration(minutes: int) -> str:
    """Форматирует длительность в человекочитаемый вид (например: '45 мин', '2.5 ч', '3 ч')."""
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes / 60.0
    if hours.is_integer():
        return f"{int(hours)} ч"
    return f"{hours:.1f} ч"


def template_night_overconsumption(
    channel_id: str,
    channel_name: str,
    current_power_kw: float,
    norm_median_kw: float,
    pct_diff: float,
    duration_minutes: int = 0,
) -> str:
    """Шаблон триггера 1: Завышенная ночная база -> забытый прибор."""
    dur_str = f" в течение {format_duration(duration_minutes)}" if duration_minutes > 0 else ""
    return (
        f"Канал {channel_name} (№{channel_id}): ночное потребление ({current_power_kw:.3f} кВт) "
        f"превышает норму ({norm_median_kw:.3f} кВт) на {pct_diff:.0f}%{dur_str}. "
        f"Возможно, забыт включённым прибор."
    )


def template_cyclicity_breakdown(
    channel_id: str,
    channel_name: str,
    duration_minutes: int,
    normal_cycle_min: Union[int, float],
) -> str:
    """Шаблон триггера 2: Нарушение цикличности -> подозрение на поломку."""
    dur_str = format_duration(duration_minutes)
    cycle_str = f"{int(normal_cycle_min)}" if float(normal_cycle_min).is_integer() else f"{normal_cycle_min:.1f}"
    return (
        f"Канал {channel_name} (№{channel_id}): работает без остановки уже {dur_str}, "
        f"обычно отключается каждые {cycle_str} мин. "
        f"Подозрение на поломку или негерметичность."
    )


def template_daytime_overload(
    channel_id: str,
    channel_name: str,
    current_power_kw: float,
    norm_median_kw: float,
    pct_diff: float,
    duration_minutes: int = 0,
) -> str:
    """Шаблон триггера 3: Отклонение в рабочие часы -> нештатный режим."""
    dur_str = f" в течение {format_duration(duration_minutes)}" if duration_minutes > 0 else ""
    return (
        f"Канал {channel_name} (№{channel_id}): потребление в рабочие часы ({current_power_kw:.3f} кВт) "
        f"превышает норму ({norm_median_kw:.3f} кВт) на {pct_diff:.0f}%{dur_str}. "
        f"Нештатный режим или перегрузка оборудования."
    )
