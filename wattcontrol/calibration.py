"""Модуль 7-дневной пассивной калибровки энергопотребления «ВаттКонтроль».

Реализует чистую математическую статистику (без нейросетей):
- Разделение профилей день/ночь.
- Определение медианы, стандартного отклонения и коридора нормы.
- Автоматический анализ цикличности (ON/OFF фазы компрессора).
- Автоматическая классификация типа канала: BASE_24_7, CYCLIC, WORKING_HOURS.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from wattcontrol.models import (
    ChannelProfile,
    ChannelType,
    CycleStats,
    TelemetryReading,
    TimeWindowStats,
)


class CalibrationEngine:
    """Движок калибровки индивидуальной нормы по каналу на основе 7 дней данных."""

    def __init__(
        self,
        night_start_hour: int = 23,
        night_end_hour: int = 7,
        night_overconsumption_ratio: float = 1.40,  # +40% к ночной норме
    ):
        self.night_start_hour = night_start_hour
        self.night_end_hour = night_end_hour
        self.night_overconsumption_ratio = night_overconsumption_ratio

    def is_night(self, dt: datetime) -> bool:
        """Проверяет, попадает ли время в интервал тихих ночных часов."""
        if self.night_start_hour > self.night_end_hour:
            return dt.hour >= self.night_start_hour or dt.hour < self.night_end_hour
        return self.night_start_hour <= dt.hour < self.night_end_hour

    def calibrate_channel(
        self,
        channel_id: str,
        channel_name: str,
        readings: List[TelemetryReading],
    ) -> ChannelProfile:
        """Проводит полную калибровку одного канала по ряду измерений."""
        if not readings:
            raise ValueError(f"Пустой список измерений для канала {channel_id}")

        # Сортируем измерения по времени
        sorted_readings = sorted(readings, key=lambda r: r.timestamp)
        start_time = sorted_readings[0].timestamp
        end_time = sorted_readings[-1].timestamp

        all_powers = [r.power for r in sorted_readings]
        night_powers = [r.power for r in sorted_readings if self.is_night(r.timestamp)]
        day_powers = [r.power for r in sorted_readings if not self.is_night(r.timestamp)]

        overall_stats = self._calc_stats(all_powers)
        night_stats = self._calc_stats(night_powers) if night_powers else overall_stats
        day_stats = self._calc_stats(day_powers) if day_powers else overall_stats

        # Анализ цикличности
        cycle_stats = self._analyze_cyclicity(sorted_readings)

        # Классификация типа канала
        channel_type = self._classify_channel(
            overall_stats=overall_stats,
            day_stats=day_stats,
            night_stats=night_stats,
            cycle_stats=cycle_stats,
            total_duration_days=max(1.0, (end_time - start_time).total_seconds() / 86400.0),
        )

        # Расчет порогов аномалий
        # 1. Порог ночной базы: превышение на 40% от ночной медианы (с защитой от околонулевых баз)
        if night_stats.median_power > 0.02:
            night_threshold = night_stats.median_power * self.night_overconsumption_ratio
        else:
            night_threshold = night_stats.median_power + 0.10  # абсолютный порог 100 Вт для нулевых баз

        # 2. Порог дневного перегруза (медиана + 3 std или +35% от медианы)
        daytime_threshold = max(
            day_stats.median_power * 1.35,
            day_stats.median_power + 3.0 * day_stats.std_power,
            0.15,
        )

        return ChannelProfile(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_type=channel_type,
            calibration_start=start_time,
            calibration_end=end_time,
            total_samples=len(sorted_readings),
            night_stats=night_stats,
            day_stats=day_stats,
            overall_stats=overall_stats,
            cycle_stats=cycle_stats,
            night_baseline_threshold_kw=night_threshold,
            daytime_overload_threshold_kw=daytime_threshold,
        )

    def _calc_stats(self, values: List[float]) -> TimeWindowStats:
        """Вычисляет робастные статистики временного окна."""
        if not values:
            return TimeWindowStats()

        s_vals = sorted(values)
        n = len(s_vals)
        min_v = s_vals[0]
        max_v = s_vals[-1]
        mean_v = sum(s_vals) / n
        median_v = statistics.median(s_vals)
        std_v = statistics.stdev(s_vals) if n > 1 else 0.0

        # Квартили
        q25 = s_vals[int(n * 0.25)]
        q75 = s_vals[int(n * 0.75)]

        return TimeWindowStats(
            count=n,
            min_power=min_v,
            max_power=max_v,
            median_power=median_v,
            mean_power=mean_v,
            std_power=std_v,
            q25=q25,
            q75=q75,
        )

    def _analyze_cyclicity(self, readings: List[TelemetryReading]) -> Optional[CycleStats]:
        """Анализирует циклический режим (ON / OFF) работы оборудования."""
        if len(readings) < 60:
            return None

        powers = [r.power for r in readings]
        p_min = min(powers)
        p_max = max(powers)

        # Если размах мал (< 50 Вт), цикличность отсутствует
        if (p_max - p_min) < 0.05:
            return None

        # Разделяющий порог между активным состоянием и простоем
        # Для компрессоров холодильников: активная мощность ~0.8 кВт, простой ~0.01 кВт.
        # Берем порог отсечки на уровне 30% между минимумом и максимумом
        threshold = p_min + 0.30 * (p_max - p_min)

        # Поиск интервалов включения и выключения
        on_intervals_min: List[int] = []
        off_intervals_min: List[int] = []
        active_powers: List[float] = []
        idle_powers: List[float] = []

        is_currently_on = readings[0].power >= threshold
        current_streak = 0

        for r in readings:
            is_reading_on = r.power >= threshold
            if is_reading_on:
                active_powers.append(r.power)
            else:
                idle_powers.append(r.power)

            if is_reading_on == is_currently_on:
                current_streak += 1
            else:
                if is_currently_on:
                    on_intervals_min.append(current_streak)
                else:
                    off_intervals_min.append(current_streak)
                is_currently_on = is_reading_on
                current_streak = 1

        # Учитываем последний отрезок
        if is_currently_on:
            on_intervals_min.append(current_streak)
        else:
            off_intervals_min.append(current_streak)

        if not on_intervals_min or not off_intervals_min:
            return None

        # Фильтруем слишком короткие помехи (< 2 минут)
        clean_on = [m for m in on_intervals_min if m >= 2]
        clean_off = [m for m in off_intervals_min if m >= 2]

        if len(clean_on) < 5 or len(clean_off) < 5:
            return None

        median_on = float(statistics.median(clean_on))
        mean_on = float(sum(clean_on) / len(clean_on))
        std_on = float(statistics.stdev(clean_on)) if len(clean_on) > 1 else 0.0

        median_off = float(statistics.median(clean_off))
        mean_off = float(sum(clean_off) / len(clean_off))

        total_on_time = sum(clean_on)
        total_cycle_time = sum(clean_on) + sum(clean_off)
        duty_cycle = total_on_time / total_cycle_time if total_cycle_time > 0 else 0.0

        # Максимально допустимая непрерывная работа до фиксации аномалии:
        # медиана + 3 std, но не менее 2.2 * медианы и не менее 45 минут
        max_allowed_on = max(
            median_on + 3.0 * std_on,
            median_on * 2.2,
            45.0,
        )

        return CycleStats(
            cycle_count=len(clean_on),
            mean_on_minutes=mean_on,
            median_on_minutes=median_on,
            std_on_minutes=std_on,
            mean_off_minutes=mean_off,
            median_off_minutes=median_off,
            duty_cycle=duty_cycle,
            on_power_median=statistics.median(active_powers) if active_powers else p_max,
            off_power_median=statistics.median(idle_powers) if idle_powers else p_min,
            max_allowed_on_minutes=max_allowed_on,
        )

    def _classify_channel(
        self,
        overall_stats: TimeWindowStats,
        day_stats: TimeWindowStats,
        night_stats: TimeWindowStats,
        cycle_stats: Optional[CycleStats],
        total_duration_days: float,
    ) -> ChannelType:
        """Автоматическая классификация канала на основе статистических свойств."""
        # 1. Проверяем, засыпает ли прибор ночью (ночное затишье).
        # Холодильники и морозильники работают 24/7 и ночью непременно включают компрессор.
        # Напротив, рабочее оборудование (кофемашины, свет, грили, витрины с подогревом, подъёмники)
        # ночью выключено (потребление близко к 0 или в разы ниже дневного).
        is_night_dormant = (
            night_stats.max_power < 0.15 and day_stats.max_power > 0.5
        ) or (
            night_stats.mean_power < 0.05 and day_stats.mean_power > 0.2
        ) or (
            day_stats.mean_power > max(0.01, night_stats.mean_power) * 3.0 and night_stats.max_power < 0.25
        )
        if is_night_dormant:
            return ChannelType.WORKING_HOURS

        # 2. Проверяем постоянную фоновую нагрузку 24/7 (роутеры, кассы, видеонаблюдение)
        # Признаки: ночная медиана близка к дневной, малый коэффициент вариации CV < 0.25
        mean_p = overall_stats.mean_power
        if mean_p > 0.01:
            cv = overall_stats.std_power / mean_p
            day_night_diff = abs(day_stats.median_power - night_stats.median_power) / max(0.01, mean_p)
            if cv < 0.25 and day_night_diff < 0.30:
                return ChannelType.BASE_24_7

        # 3. Проверяем цикличность (холодильники, витрины, компрессоры с регулярными циклами 24/7)
        if cycle_stats and cycle_stats.cycle_count >= int(total_duration_days * 5):
            if cycle_stats.std_on_minutes / max(1.0, cycle_stats.median_on_minutes) < 0.65:
                return ChannelType.CYCLIC

        return ChannelType.WORKING_HOURS
