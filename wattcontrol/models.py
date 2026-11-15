"""Модели данных системы «ВаттКонтроль».

Определяют типы телеметрии, нормативных профилей, аномалий и состояний дашборда.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List


class ChannelType(str, Enum):
    """Тип канала по характеру нагрузки, определяемый автоматически."""
    BASE_24_7 = "BASE_24_7"          # Постоянная нагрузка 24/7 (роутеры, кассы, серверы)
    CYCLIC = "CYCLIC"                # Циклическая нагрузка (холодильники, витрины, компрессоры)
    WORKING_HOURS = "WORKING_HOURS"  # Оборудование рабочих часов (кофемашины, свет, грили, подъёмники)
    UNKNOWN = "UNKNOWN"              # Недостаточно данных для классификации

    @property
    def label_ru(self) -> str:
        labels = {
            ChannelType.BASE_24_7: "Постоянная база 24/7",
            ChannelType.CYCLIC: "Циклический прибор",
            ChannelType.WORKING_HOURS: "Рабочее оборудование",
            ChannelType.UNKNOWN: "Не классифицирован",
        }
        return labels.get(self, "Неизвестно")


class AnomalyType(str, Enum):
    """Три ключевых типа триггеров аномалий."""
    NIGHT_OVERCONSUMPTION = "NIGHT_OVERCONSUMPTION"  # Завышенная ночная база (забытый прибор)
    CYCLICITY_BREAKDOWN = "CYCLICITY_BREAKDOWN"      # Нарушение цикличности (поломка компрессора)
    DAYTIME_OVERLOAD = "DAYTIME_OVERLOAD"            # Отклонение в рабочие часы (перегрузка/сбой)

    @property
    def label_ru(self) -> str:
        labels = {
            AnomalyType.NIGHT_OVERCONSUMPTION: "Завышенная ночная база",
            AnomalyType.CYCLICITY_BREAKDOWN: "Нарушение цикличности",
            AnomalyType.DAYTIME_OVERLOAD: "Отклонение в рабочие часы",
        }
        return labels.get(self, "Аномалия")


class ChannelStatus(str, Enum):
    """Статус канала для сводной таблицы дашборда."""
    NORMAL = "NORMAL"            # 🟢 Норма
    ANOMALY = "ANOMALY"          # 🔴 Отклонение
    CALIBRATING = "CALIBRATING"  # 🟡 Калибровка (первые 7 дней)


@dataclass
class TelemetryReading:
    """Ежеминутный срез измерений по конкретному каналу/фазе."""
    timestamp: datetime
    channel_id: str
    voltage: float           # Напряжение, В
    current: float           # Ток, А
    power: float             # Активная мощность, кВт
    energy_daily: Optional[float] = None  # Суточное потребление (если передано), кВт⋅ч

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "channel_id": self.channel_id,
            "voltage": round(self.voltage, 2),
            "current": round(self.current, 3),
            "power": round(self.power, 4),
            "energy_daily": round(self.energy_daily, 3) if self.energy_daily is not None else None,
        }


@dataclass
class TimeWindowStats:
    """Статистика потребления мощности в заданном временном окне (кВт)."""
    count: int = 0
    min_power: float = 0.0
    max_power: float = 0.0
    median_power: float = 0.0
    mean_power: float = 0.0
    std_power: float = 0.0
    q25: float = 0.0
    q75: float = 0.0

    @property
    def corridor_lower(self) -> float:
        """Нижняя граница коридора нормы (медиана - 1 std, не ниже min)."""
        return max(0.0, self.median_power - self.std_power)

    @property
    def corridor_upper(self) -> float:
        """Верхняя граница коридора нормы (медиана + 1 std)."""
        return self.median_power + self.std_power


@dataclass
class CycleStats:
    """Статистика циклического режима для приборов типа холодильников."""
    cycle_count: int = 0
    mean_on_minutes: float = 0.0
    median_on_minutes: float = 0.0
    std_on_minutes: float = 0.0
    mean_off_minutes: float = 0.0
    median_off_minutes: float = 0.0
    duty_cycle: float = 0.0         # Доля времени включения (0..1)
    on_power_median: float = 0.0    # Мощность в активной фазе (кВт)
    off_power_median: float = 0.0   # Мощность в фазе простоя (кВт)
    max_allowed_on_minutes: float = 0.0  # Порог непрерывной работы до триггера тревоги


@dataclass
class ChannelProfile:
    """Результат 7-дневной пассивной калибровки канала."""
    channel_id: str
    channel_name: str
    channel_type: ChannelType
    calibration_start: datetime
    calibration_end: datetime
    total_samples: int
    night_stats: TimeWindowStats     # 23:00 - 07:00
    day_stats: TimeWindowStats       # 07:00 - 23:00
    overall_stats: TimeWindowStats
    cycle_stats: Optional[CycleStats] = None
    night_baseline_threshold_kw: float = 0.0
    daytime_overload_threshold_kw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "channel_type": self.channel_type.value,
            "channel_type_label": self.channel_type.label_ru,
            "total_samples": self.total_samples,
            "night_median_kw": round(self.night_stats.median_power, 4),
            "night_threshold_kw": round(self.night_baseline_threshold_kw, 4),
            "day_median_kw": round(self.day_stats.median_power, 4),
            "day_std_kw": round(self.day_stats.std_power, 4),
            "day_threshold_kw": round(self.daytime_overload_threshold_kw, 4),
            "cycle_stats": {
                "median_on_minutes": round(self.cycle_stats.median_on_minutes, 1),
                "median_off_minutes": round(self.cycle_stats.median_off_minutes, 1),
                "duty_cycle": round(self.cycle_stats.duty_cycle, 2),
                "max_allowed_on_minutes": round(self.cycle_stats.max_allowed_on_minutes, 1),
            } if self.cycle_stats else None,
        }


@dataclass
class AnomalyEvent:
    """Событие обнаруженной аномалии с шаблонным описанием."""
    anomaly_id: str
    channel_id: str
    channel_name: str
    anomaly_type: AnomalyType
    start_time: datetime
    last_updated_time: datetime
    duration_minutes: int
    current_power_kw: float
    normal_median_kw: float
    pct_difference: float
    description: str
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "anomaly_type": self.anomaly_type.value,
            "anomaly_type_label": self.anomaly_type.label_ru,
            "start_time": self.start_time.isoformat(),
            "last_updated_time": self.last_updated_time.isoformat(),
            "duration_minutes": self.duration_minutes,
            "current_power_kw": round(self.current_power_kw, 3),
            "normal_median_kw": round(self.normal_median_kw, 3),
            "pct_difference": round(self.pct_difference, 1),
            "description": self.description,
            "is_active": self.is_active,
        }


@dataclass
class ChannelDashboardState:
    """Срез текущего состояния канала для экрана сводной таблицы."""
    channel_id: str
    channel_name: str
    channel_type: ChannelType
    status: ChannelStatus
    current_voltage: float
    current_current: float
    current_power: float
    norm_min_kw: float
    norm_median_kw: float
    norm_max_kw: float
    active_anomaly: Optional[AnomalyEvent] = None
    last_anomaly_description: str = "Норма"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "channel_type": self.channel_type.value,
            "channel_type_label": self.channel_type.label_ru,
            "status": self.status.value,
            "status_badge": "🟢 Норма" if self.status == ChannelStatus.NORMAL else "🔴 Отклонение",
            "current_voltage": round(self.current_voltage, 1),
            "current_current": round(self.current_current, 3),
            "current_power": round(self.current_power, 3),
            "norm_min_kw": round(self.norm_min_kw, 3),
            "norm_median_kw": round(self.norm_median_kw, 3),
            "norm_max_kw": round(self.norm_max_kw, 3),
            "last_anomaly_description": self.last_anomaly_description,
        }
