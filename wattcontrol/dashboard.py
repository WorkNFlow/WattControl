"""Формирование данных для двух экранов веб-дашборда «ВаттКонтроль».

1. Экран «График»:
   - Факт потребления (сплошная линия).
   - Закрашенный «коридор нормы» (медиана ± стандартное отклонение).
   - Маркеры в точках аномалий с подсказками (тип, время начала, длительность).
2. Экран «Сводная таблица»:
   - Тип канала, текущее значение (кВт, А, В).
   - Норма (мин — медиана — макс).
   - Статус (🟢 Норма / 🔴 Отклонение).
   - Описание последней аномалии.
Никаких рублей и тарифов — строго физические величины.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from wattcontrol.detector import AnomalyDetector
from wattcontrol.models import (
    AnomalyEvent,
    ChannelProfile,
    TelemetryReading,
)


class DashboardDataExporter:
    """Экспортер данных для веб-дашборда."""

    @staticmethod
    def build_chart_data(
        channel_id: str,
        readings: List[TelemetryReading],
        profile: ChannelProfile,
        anomalies: List[AnomalyEvent],
    ) -> Dict[str, Any]:
        """Формирует данные для графика конкретного канала."""
        timestamps: List[str] = []
        actual_kw: List[float] = []
        corridor_lower: List[float] = []
        corridor_upper: List[float] = []
        median_line: List[float] = []

        # Выбираем релевантную норму (день/ночь) для каждой точки
        for r in readings:
            timestamps.append(r.timestamp.strftime("%Y-%m-%d %H:%M"))
            actual_kw.append(round(r.power, 4))

            # Определяем, ночная ли это точка
            h = r.timestamp.hour
            is_night = h < 7 or h >= 23
            stats = profile.night_stats if is_night else profile.day_stats

            med = stats.median_power
            low = max(0.0, med - stats.std_power)
            high = med + stats.std_power

            median_line.append(round(med, 4))
            corridor_lower.append(round(low, 4))
            corridor_upper.append(round(high, 4))

        # Маркеры аномалий
        anomaly_markers: List[Dict[str, Any]] = []
        for anom in anomalies:
            if anom.channel_id == channel_id:
                anomaly_markers.append({
                    "anomaly_id": anom.anomaly_id,
                    "type": anom.anomaly_type.value,
                    "type_label": anom.anomaly_type.label_ru,
                    "start_time": anom.start_time.strftime("%Y-%m-%d %H:%M"),
                    "last_time": anom.last_updated_time.strftime("%Y-%m-%d %H:%M"),
                    "duration_minutes": anom.duration_minutes,
                    "power_kw": round(anom.current_power_kw, 3),
                    "description": anom.description,
                    "tooltip": (
                        f"⚠️ {anom.anomaly_type.label_ru}\n"
                        f"Начало: {anom.start_time.strftime('%H:%M')}\n"
                        f"Длительность: {anom.duration_minutes} мин\n"
                        f"Мощность: {anom.current_power_kw:.3f} кВт\n"
                        f"{anom.description}"
                    ),
                })

        return {
            "channel_id": channel_id,
            "channel_name": profile.channel_name,
            "channel_type": profile.channel_type.value,
            "channel_type_label": profile.channel_type.label_ru,
            "timestamps": timestamps,
            "actual_kw": actual_kw,
            "corridor_lower": corridor_lower,
            "corridor_upper": corridor_upper,
            "median_line": median_line,
            "anomaly_markers": anomaly_markers,
        }

    @staticmethod
    def build_summary_table(detector: AnomalyDetector) -> List[Dict[str, Any]]:
        """Формирует данные для сводной таблицы всех каналов."""
        states = detector.get_all_dashboard_states()
        rows: List[Dict[str, Any]] = []

        for st in states:
            rows.append({
                "channel_id": st.channel_id,
                "channel_name": st.channel_name,
                "channel_type_label": st.channel_type.label_ru,
                "status_badge": "🟢 Норма" if st.status.value == "NORMAL" else "🔴 Отклонение",
                "status_code": st.status.value,
                "current_voltage_v": round(st.current_voltage, 1),
                "current_current_a": round(st.current_current, 3),
                "current_power_kw": round(st.current_power, 3),
                "norm_range_str": f"{st.norm_min_kw:.2f} – {st.norm_median_kw:.2f} – {st.norm_max_kw:.2f} кВт",
                "last_anomaly_description": st.last_anomaly_description,
            })

        return rows

    @staticmethod
    def export_full_dashboard_payload(
        detector: AnomalyDetector,
        readings_by_channel: Dict[str, List[TelemetryReading]],
        anomalies_history: List[AnomalyEvent],
        snapshots: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """Собирает полный JSON-пакет данных для веб-интерфейса."""
        charts = {}
        for cid, profile in detector.profiles.items():
            ch_readings = readings_by_channel.get(cid, [])
            charts[cid] = DashboardDataExporter.build_chart_data(
                channel_id=cid,
                readings=ch_readings,
                profile=profile,
                anomalies=anomalies_history,
            )

        summary_table = DashboardDataExporter.build_summary_table(detector)

        return {
            "summary_table": summary_table,
            "snapshots": snapshots or {"current": summary_table},
            "charts": charts,
        }
