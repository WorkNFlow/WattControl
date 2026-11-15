#!/usr/bin/env python3
"""Сквозной демонстрационный сценарий сервиса «ВаттКонтроль».

Демонстрирует:
1. Загрузку 7 дней нормальных данных (10 080 точек на канал).
2. Автоматическую калибровку индивидуальных норм и классификацию каналов (чистая статистика).
3. Потоковый мониторинг 8-го дня с детекцией 3 целевых сценариев аномалий:
   - Сценарий 1: Забытый прибор ночью на ch_base (+40%+ к базе).
   - Сценарий 2: Поломка/разгерметизация компрессора холодильника ch_fridge (непрерывная работа 4 часа).
   - Сценарий 3: Дневной перегруз оборудования на ch_coffee (> 4 кВт).
4. Вывод данных для 2-х экранов дашборда (консоль + генерация автономного dashboard.html).
"""

import os
from datetime import datetime, timedelta

from wattcontrol.adapter import SyntheticTelemetryGenerator
from wattcontrol.calibration import CalibrationEngine
from wattcontrol.dashboard import DashboardDataExporter
from wattcontrol.detector import AnomalyDetector
from wattcontrol.visualizer import HTMLDashboardGenerator


def main() -> None:
    print("=" * 76)
    print("   ⚡ ПРОЕКТ «ВАТТКОНТРОЛЬ» — АЛГОРИТМ ДЕТЕКЦИИ АНОМАЛИЙ ДЛЯ МАЛОГО БИЗНЕСА")
    print("   (Чистая статистика: медиана, стандартное отклонение, цикличность)")
    print("=" * 76)

    # 1. Генерация 7 дней нормальной телеметрии
    print("\n[ШАГ 1] Пассивный сбор 7 дней телеметрии (интервал: 1 минута)...")
    generator = SyntheticTelemetryGenerator(seed=42)
    start_time = datetime(2026, 11, 1, 0, 0, 0)

    calibration_readings = generator.generate_calibration_data(
        start_time=start_time,
        days=7,
        sample_step_minutes=1,
    )

    for cid, r_list in calibration_readings.items():
        name = generator.CHANNEL_NAMES[cid]
        print(f"  • {name} (ID: {cid}): получено {len(r_list)} измерений")

    # 2. Калибровка нормы
    print("\n[ШАГ 2] Калибровка индивидуальной нормы по каждому каналу...")
    engine = CalibrationEngine()
    profiles = {}

    for cid, r_list in calibration_readings.items():
        name = generator.CHANNEL_NAMES[cid]
        profile = engine.calibrate_channel(cid, name, r_list)
        profiles[cid] = profile

        print(f"\n  📊 Профиль канала: {name} (ID: {cid})")
        print(f"     Определённый тип: {profile.channel_type.label_ru} [{profile.channel_type.value}]")
        print(f"     Ночная норма (медиана): {profile.night_stats.median_power:.3f} кВт (порог аномалии: {profile.night_baseline_threshold_kw:.3f} кВт)")
        print(f"     Дневная норма (медиана ± σ): {profile.day_stats.median_power:.3f} ± {profile.day_stats.std_power:.3f} кВт")
        if profile.cycle_stats:
            cs = profile.cycle_stats
            print(f"     Цикличность: {cs.median_on_minutes:.0f} мин ВКЛ / {cs.median_off_minutes:.0f} мин ВЫКЛ "
                  f"(макс. допустимо без остановки: {cs.max_allowed_on_minutes:.0f} мин)")

    # 3. Запуск потокового детектора на 8-й день с инъекцией инцидентов
    print("\n" + "=" * 76)
    print("[ШАГ 3] Мониторинг 8-го дня: потоковая обработка и проверка 3-х триггеров")
    print("=" * 76)

    day8_start = start_time + timedelta(days=7)
    day8_data = generator.generate_day8_with_anomalies(day8_start)

    detector = AnomalyDetector(profiles=profiles)
    all_triggered_anomalies = []
    snapshots = {}

    # Обрабатываем поминутно в хронологическом порядке
    total_minutes_day8 = 24 * 60
    for minute_idx in range(total_minutes_day8):
        current_time = day8_start + timedelta(minutes=minute_idx)
        for cid in ["ch_fridge", "ch_coffee", "ch_base"]:
            reading = day8_data[cid][minute_idx]
            new_anomalies = detector.process_reading(reading)
            if new_anomalies:
                for a in new_anomalies:
                    all_triggered_anomalies.append(a)
                    print(f"\n🚨 [СРАБОТАЛ ТРИГГЕР] {current_time.strftime('%H:%M')} — {a.anomaly_type.label_ru}:")
                    print(f"   {a.description}")

        # Фиксируем срез в момент ночного инцидента (03:30)
        if minute_idx == 3 * 60 + 30:
            snapshots["night_incident"] = DashboardDataExporter.build_summary_table(detector)

        # Фиксируем срез в момент дневного перегруза (12:30)
        if minute_idx == 12 * 60 + 30:
            snapshots["day_incident"] = DashboardDataExporter.build_summary_table(detector)

    # Фиксируем срез на конец суток (23:59)
    snapshots["end_of_day"] = DashboardDataExporter.build_summary_table(detector)

    # 4. Вывод данных для Экрана 1: Сводная таблица во время ночного инцидента
    print("\n" + "=" * 76)
    print("   ЭКРАН 1: СВОДНАЯ ТАБЛИЦА СТАТУСОВ КАНАЛОВ (Срез в 03:30 — активная авария)")
    print("=" * 76)

    summary_rows = snapshots["night_incident"]
    header_fmt = "{:<25} {:<18} {:<14} {:<24} {:<12}"
    row_fmt = "{:<25} {:<18} {:<14} {:<24} {:<12}"
    print(header_fmt.format("Канал", "Тип", "Текущее", "Норма (мин-мед-макс)", "Статус"))
    print("-" * 95)
    for row in summary_rows:
        print(row_fmt.format(
            row["channel_name"][:24],
            row["channel_type_label"][:17],
            f"{row['current_power_kw']:.2f} кВт",
            row["norm_range_str"],
            row["status_badge"],
        ))
        if row["status_code"] == "ANOMALY":
            print(f"   ↳ ⚠️ {row['last_anomaly_description']}")
    print("-" * 95)

    # 5. Экспорт дашборда
    print("\n[ШАГ 4] Генерация интерактивного HTML веб-дашборда (2 экрана)...")
    payload = DashboardDataExporter.export_full_dashboard_payload(
        detector=detector,
        readings_by_channel=day8_data,
        anomalies_history=all_triggered_anomalies,
        snapshots=snapshots,
    )

    output_html = os.path.abspath("dashboard.html")
    HTMLDashboardGenerator.generate_html(payload, output_html)

    print(f"✅ Готово! Автономный веб-дашборд сохранён в:")
    print(f"   file://{output_html}")
    print("\nВы можете открыть dashboard.html в любом браузере, чтобы продемонстрировать:")
    print(" • Сводную таблицу со статусами 🟢/🔴 и переключателем инцидентов (03:30 / 12:30 / 23:59).")
    print(" • График с закрашенным коридором нормы (Медиана ± 1σ) и точками сбоев с тултипами.")


if __name__ == "__main__":
    main()
