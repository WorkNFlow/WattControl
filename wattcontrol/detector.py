"""Движок детекции аномалий в реальном времени сервиса «ВаттКонтроль».

Реализует потоковый мониторинг 1-минутных показаний по трем триггерам:
1. Завышенная ночная база (Trigger 1) -> забытый прибор.
2. Нарушение цикличности (Trigger 2) -> подозрение на поломку компрессора/витрины.
3. Отклонение в рабочие часы (Trigger 3) -> нештатный режим / перегрузка.
С дебаунсингом (защита от кратковременных пусковых токов) и шаблонизатором текста.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from wattcontrol.models import (
    AnomalyEvent,
    AnomalyType,
    ChannelDashboardState,
    ChannelProfile,
    ChannelStatus,
    ChannelType,
    TelemetryReading,
)
from wattcontrol.templates import (
    template_cyclicity_breakdown,
    template_daytime_overload,
    template_night_overconsumption,
)


class ChannelDetectorState:
    """Внутреннее состояние потокового анализатора для одного канала."""

    def __init__(self, profile: ChannelProfile):
        self.profile = profile

        # Трекер ночного режима
        self.night_streak_minutes: int = 0
        self.night_start_time: Optional[datetime] = None

        # Трекер дневного перегруза
        self.day_overload_streak_minutes: int = 0
        self.day_overload_start_time: Optional[datetime] = None

        # Трекер цикличности (компрессора)
        self.is_compressor_on: bool = False
        self.continuous_on_minutes: int = 0
        self.on_start_time: Optional[datetime] = None

        # Активные аномалии {AnomalyType: AnomalyEvent}
        self.active_anomalies: Dict[AnomalyType, AnomalyEvent] = {}

        # История зафиксированных аномалий
        self.anomaly_history: List[AnomalyEvent] = []

        # Последнее измерение
        self.last_reading: Optional[TelemetryReading] = None


class AnomalyDetector:
    """Основной класс детектора аномалий «ВаттКонтроль»."""

    def __init__(
        self,
        profiles: Dict[str, ChannelProfile],
        night_start_hour: int = 23,
        night_end_hour: int = 7,
        night_debounce_minutes: int = 15,    # Нужно 15 минут устойчивого превышения ночью
        day_debounce_minutes: int = 10,      # Нужно 10 минут превышения днем
    ):
        self.profiles = profiles
        self.night_start_hour = night_start_hour
        self.night_end_hour = night_end_hour
        self.night_debounce_minutes = night_debounce_minutes
        self.day_debounce_minutes = day_debounce_minutes

        self.channel_states: Dict[str, ChannelDetectorState] = {
            cid: ChannelDetectorState(profile) for cid, profile in profiles.items()
        }

    def is_night(self, dt: datetime) -> bool:
        """Проверяет принадлежность времени к ночному окну."""
        if self.night_start_hour > self.night_end_hour:
            return dt.hour >= self.night_start_hour or dt.hour < self.night_end_hour
        return self.night_start_hour <= dt.hour < self.night_end_hour

    def process_reading(self, reading: TelemetryReading) -> List[AnomalyEvent]:
        """Обрабатывает одно ежеминутное измерение канала и возвращает возникшие/обновленные аномалии."""
        channel_id = reading.channel_id
        if channel_id not in self.channel_states:
            return []

        state = self.channel_states[channel_id]
        profile = state.profile
        state.last_reading = reading
        now = reading.timestamp
        current_power = reading.power
        is_night_time = self.is_night(now)

        newly_triggered: List[AnomalyEvent] = []

        # =====================================================================
        # ТРИГГЕР 1: Завышенная ночная база (забытый прибор)
        # =====================================================================
        if is_night_time:
            # Проверяем превышение ночного порога (+40% к норме)
            if current_power >= profile.night_baseline_threshold_kw:
                if state.night_streak_minutes == 0:
                    state.night_start_time = now
                state.night_streak_minutes += 1

                if state.night_streak_minutes >= self.night_debounce_minutes:
                    pct_diff = (
                        (current_power - profile.night_stats.median_power)
                        / max(0.001, profile.night_stats.median_power)
                    ) * 100.0

                    if AnomalyType.NIGHT_OVERCONSUMPTION not in state.active_anomalies:
                        desc = template_night_overconsumption(
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            current_power_kw=current_power,
                            norm_median_kw=profile.night_stats.median_power,
                            pct_diff=pct_diff,
                            duration_minutes=state.night_streak_minutes,
                        )
                        event = AnomalyEvent(
                            anomaly_id=str(uuid.uuid4())[:8],
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            anomaly_type=AnomalyType.NIGHT_OVERCONSUMPTION,
                            start_time=state.night_start_time or now,
                            last_updated_time=now,
                            duration_minutes=state.night_streak_minutes,
                            current_power_kw=current_power,
                            normal_median_kw=profile.night_stats.median_power,
                            pct_difference=pct_diff,
                            description=desc,
                            is_active=True,
                        )
                        state.active_anomalies[AnomalyType.NIGHT_OVERCONSUMPTION] = event
                        state.anomaly_history.append(event)
                        newly_triggered.append(event)
                    else:
                        # Обновляем длительность существующей аномалии
                        existing = state.active_anomalies[AnomalyType.NIGHT_OVERCONSUMPTION]
                        existing.last_updated_time = now
                        existing.duration_minutes = state.night_streak_minutes
                        existing.current_power_kw = current_power
                        existing.pct_difference = pct_diff
                        existing.description = template_night_overconsumption(
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            current_power_kw=current_power,
                            norm_median_kw=profile.night_stats.median_power,
                            pct_diff=pct_diff,
                            duration_minutes=state.night_streak_minutes,
                        )
            else:
                # Ночное потребление вернулось в норму
                state.night_streak_minutes = 0
                state.night_start_time = None
                if AnomalyType.NIGHT_OVERCONSUMPTION in state.active_anomalies:
                    state.active_anomalies[AnomalyType.NIGHT_OVERCONSUMPTION].is_active = False
                    del state.active_anomalies[AnomalyType.NIGHT_OVERCONSUMPTION]
        else:
            # Наступило утро
            state.night_streak_minutes = 0
            state.night_start_time = None
            if AnomalyType.NIGHT_OVERCONSUMPTION in state.active_anomalies:
                state.active_anomalies[AnomalyType.NIGHT_OVERCONSUMPTION].is_active = False
                del state.active_anomalies[AnomalyType.NIGHT_OVERCONSUMPTION]

        # =====================================================================
        # ТРИГГЕР 2: Нарушение цикличности (поломка компрессора / витрины)
        # =====================================================================
        if profile.channel_type == ChannelType.CYCLIC and profile.cycle_stats:
            cstats = profile.cycle_stats
            # Порог отсечки активности компрессора
            on_cutoff = cstats.off_power_median + 0.35 * (cstats.on_power_median - cstats.off_power_median)

            if current_power >= on_cutoff:
                # Компрессор включен
                if not state.is_compressor_on:
                    state.is_compressor_on = True
                    state.continuous_on_minutes = 0
                    state.on_start_time = now

                state.continuous_on_minutes += 1

                # Превышение допустимой длительности непрерывной работы
                if state.continuous_on_minutes > cstats.max_allowed_on_minutes:
                    if AnomalyType.CYCLICITY_BREAKDOWN not in state.active_anomalies:
                        desc = template_cyclicity_breakdown(
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            duration_minutes=state.continuous_on_minutes,
                            normal_cycle_min=cstats.median_on_minutes,
                        )
                        event = AnomalyEvent(
                            anomaly_id=str(uuid.uuid4())[:8],
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            anomaly_type=AnomalyType.CYCLICITY_BREAKDOWN,
                            start_time=state.on_start_time or now,
                            last_updated_time=now,
                            duration_minutes=state.continuous_on_minutes,
                            current_power_kw=current_power,
                            normal_median_kw=cstats.on_power_median,
                            pct_difference=(
                                (state.continuous_on_minutes - cstats.median_on_minutes)
                                / max(1.0, cstats.median_on_minutes)
                            ) * 100.0,
                            description=desc,
                            is_active=True,
                        )
                        state.active_anomalies[AnomalyType.CYCLICITY_BREAKDOWN] = event
                        state.anomaly_history.append(event)
                        newly_triggered.append(event)
                    else:
                        existing = state.active_anomalies[AnomalyType.CYCLICITY_BREAKDOWN]
                        existing.last_updated_time = now
                        existing.duration_minutes = state.continuous_on_minutes
                        existing.current_power_kw = current_power
                        existing.description = template_cyclicity_breakdown(
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            duration_minutes=state.continuous_on_minutes,
                            normal_cycle_min=cstats.median_on_minutes,
                        )
            else:
                # Компрессор выключился (отдыхает)
                state.is_compressor_on = False
                state.continuous_on_minutes = 0
                state.on_start_time = None
                if AnomalyType.CYCLICITY_BREAKDOWN in state.active_anomalies:
                    state.active_anomalies[AnomalyType.CYCLICITY_BREAKDOWN].is_active = False
                    del state.active_anomalies[AnomalyType.CYCLICITY_BREAKDOWN]

        # =====================================================================
        # ТРИГГЕР 3: Отклонение в рабочие часы (перегрузка оборудования)
        # =====================================================================
        if not is_night_time:
            if current_power >= profile.daytime_overload_threshold_kw:
                if state.day_overload_streak_minutes == 0:
                    state.day_overload_start_time = now
                state.day_overload_streak_minutes += 1

                if state.day_overload_streak_minutes >= self.day_debounce_minutes:
                    pct_diff = (
                        (current_power - profile.day_stats.median_power)
                        / max(0.001, profile.day_stats.median_power)
                    ) * 100.0

                    if AnomalyType.DAYTIME_OVERLOAD not in state.active_anomalies:
                        desc = template_daytime_overload(
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            current_power_kw=current_power,
                            norm_median_kw=profile.day_stats.median_power,
                            pct_diff=pct_diff,
                            duration_minutes=state.day_overload_streak_minutes,
                        )
                        event = AnomalyEvent(
                            anomaly_id=str(uuid.uuid4())[:8],
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            anomaly_type=AnomalyType.DAYTIME_OVERLOAD,
                            start_time=state.day_overload_start_time or now,
                            last_updated_time=now,
                            duration_minutes=state.day_overload_streak_minutes,
                            current_power_kw=current_power,
                            normal_median_kw=profile.day_stats.median_power,
                            pct_difference=pct_diff,
                            description=desc,
                            is_active=True,
                        )
                        state.active_anomalies[AnomalyType.DAYTIME_OVERLOAD] = event
                        state.anomaly_history.append(event)
                        newly_triggered.append(event)
                    else:
                        existing = state.active_anomalies[AnomalyType.DAYTIME_OVERLOAD]
                        existing.last_updated_time = now
                        existing.duration_minutes = state.day_overload_streak_minutes
                        existing.current_power_kw = current_power
                        existing.pct_difference = pct_diff
                        existing.description = template_daytime_overload(
                            channel_id=channel_id,
                            channel_name=profile.channel_name,
                            current_power_kw=current_power,
                            norm_median_kw=profile.day_stats.median_power,
                            pct_diff=pct_diff,
                            duration_minutes=state.day_overload_streak_minutes,
                        )
            else:
                state.day_overload_streak_minutes = 0
                state.day_overload_start_time = None
                if AnomalyType.DAYTIME_OVERLOAD in state.active_anomalies:
                    state.active_anomalies[AnomalyType.DAYTIME_OVERLOAD].is_active = False
                    del state.active_anomalies[AnomalyType.DAYTIME_OVERLOAD]
        else:
            state.day_overload_streak_minutes = 0
            state.day_overload_start_time = None
            if AnomalyType.DAYTIME_OVERLOAD in state.active_anomalies:
                state.active_anomalies[AnomalyType.DAYTIME_OVERLOAD].is_active = False
                del state.active_anomalies[AnomalyType.DAYTIME_OVERLOAD]

        return newly_triggered

    def get_channel_dashboard_state(self, channel_id: str) -> ChannelDashboardState:
        """Возвращает текущее состояние канала для экрана сводной таблицы дашборда."""
        if channel_id not in self.channel_states:
            raise KeyError(f"Неизвестный канал: {channel_id}")

        state = self.channel_states[channel_id]
        profile = state.profile
        last_r = state.last_reading

        voltage = last_r.voltage if last_r else 220.0
        current = last_r.current if last_r else 0.0
        power = last_r.power if last_r else 0.0

        # Определяем статус канала
        is_anomaly = len(state.active_anomalies) > 0
        status = ChannelStatus.ANOMALY if is_anomaly else ChannelStatus.NORMAL

        # Активная аномалия (берем самую приоритетную/свежую)
        active_event = None
        last_desc = "В пределах нормы"
        if is_anomaly:
            # Приоритет: Нарушение цикличности > Перегруз > Ночная база
            order = [
                AnomalyType.CYCLICITY_BREAKDOWN,
                AnomalyType.DAYTIME_OVERLOAD,
                AnomalyType.NIGHT_OVERCONSUMPTION,
            ]
            for a_type in order:
                if a_type in state.active_anomalies:
                    active_event = state.active_anomalies[a_type]
                    last_desc = active_event.description
                    break
        elif state.anomaly_history:
            last_desc = f"Завершена: {state.anomaly_history[-1].description}"

        return ChannelDashboardState(
            channel_id=channel_id,
            channel_name=profile.channel_name,
            channel_type=profile.channel_type,
            status=status,
            current_voltage=voltage,
            current_current=current,
            current_power=power,
            norm_min_kw=profile.overall_stats.min_power,
            norm_median_kw=profile.overall_stats.median_power,
            norm_max_kw=profile.overall_stats.max_power,
            active_anomaly=active_event,
            last_anomaly_description=last_desc,
        )

    def get_all_dashboard_states(self) -> List[ChannelDashboardState]:
        """Возвращает срез состояний по всем каналам."""
        return [self.get_channel_dashboard_state(cid) for cid in self.channel_states]
