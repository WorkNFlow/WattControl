"""Комплексный набор тестов для сервиса «ВаттКонтроль».

Проверяет:
1. Парсинг форматов Tuya Cloud API.
2. Алгоритм 7-дневной калибровки (статистика, цикличность, классификация каналов).
3. Работу трех триггеров аномалий (ночная база, поломка компрессора, дневной перегруз).
4. Защиту от ложных срабатываний (дебаунсинг кратковременных пусковых всплесков).
5. Корректность сборки данных для веб-дашборда.
"""

from datetime import datetime, timedelta
import unittest

from wattcontrol.adapter import TuyaAdapter, SyntheticTelemetryGenerator
from wattcontrol.calibration import CalibrationEngine
from wattcontrol.detector import AnomalyDetector
from wattcontrol.models import (
    AnomalyType,
    ChannelStatus,
    ChannelType,
    TelemetryReading,
)
from wattcontrol.dashboard import DashboardDataExporter


class TestTuyaAdapter(unittest.TestCase):
    """Тестирование парсинга пакетов Tuya Cloud API."""

    def test_parse_single_phase(self):
        sample = {
            "code": "phase_a",
            "value": '{"voltage":217.6,"electricCurrent":1.000,"power":10.000}',
        }
        readings = TuyaAdapter.parse_payload(sample)
        self.assertEqual(len(readings), 1)
        r = readings[0]
        self.assertEqual(r.channel_id, "phase_a")
        self.assertAlmostEqual(r.voltage, 217.6)
        self.assertAlmostEqual(r.current, 1.000)
        self.assertAlmostEqual(r.power, 10.000)

    def test_parse_three_phase_with_energy(self):
        sample = {
            "result": [
                {"code": "phase_a", "value": '{"voltage":220.0,"electricCurrent":2.5,"power":0.55}'},
                {"code": "phase_b", "value": '{"voltage":221.0,"electricCurrent":3.0,"power":0.66}'},
                {"code": "energy_daily", "value": '{"electricTotal":14.85}'},
            ]
        }
        readings = TuyaAdapter.parse_payload(sample)
        self.assertEqual(len(readings), 2)
        self.assertEqual(readings[0].channel_id, "phase_a")
        self.assertEqual(readings[1].channel_id, "phase_b")
        self.assertAlmostEqual(readings[0].energy_daily, 14.85)

    def test_parse_malformed_graceful(self):
        sample = {"code": "phase_a", "value": "corrupted json"}
        readings = TuyaAdapter.parse_payload(sample)
        self.assertEqual(len(readings), 0)


class TestCalibrationEngine(unittest.TestCase):
    """Тестирование математики 7-дневной калибровки."""

    def setUp(self):
        self.generator = SyntheticTelemetryGenerator(seed=42)
        self.engine = CalibrationEngine()
        self.start_time = datetime(2026, 11, 1, 0, 0, 0)
        self.calib_data = self.generator.generate_calibration_data(
            start_time=self.start_time,
            days=7,
            sample_step_minutes=1,
        )

    def test_cyclic_channel_classification(self):
        # Холодильная витрина должна быть классифицирована как CYCLIC
        profile = self.engine.calibrate_channel(
            "ch_fridge",
            "Холодильник",
            self.calib_data["ch_fridge"],
        )
        self.assertEqual(profile.channel_type, ChannelType.CYCLIC)
        self.assertIsNotNone(profile.cycle_stats)
        # Нормальный цикл ~ 20-30 минут
        self.assertGreater(profile.cycle_stats.median_on_minutes, 18)
        self.assertLess(profile.cycle_stats.median_on_minutes, 32)
        # Допустимый предел непрерывной работы должен быть определен
        self.assertGreater(profile.cycle_stats.max_allowed_on_minutes, 45)

    def test_base_channel_classification(self):
        # Роутер и касса 24/7 должны быть классифицированы как BASE_24_7
        profile = self.engine.calibrate_channel(
            "ch_base",
            "Дежурная сеть",
            self.calib_data["ch_base"],
        )
        self.assertEqual(profile.channel_type, ChannelType.BASE_24_7)
        # Ночная норма должна быть около 0.12 кВт
        self.assertAlmostEqual(profile.night_stats.median_power, 0.12, delta=0.03)
        # Порог +40% к ночной норме
        self.assertAlmostEqual(profile.night_baseline_threshold_kw, profile.night_stats.median_power * 1.4, delta=0.01)

    def test_working_hours_channel_classification(self):
        # Кофемашина должна быть классифицирована как WORKING_HOURS
        profile = self.engine.calibrate_channel(
            "ch_coffee",
            "Кофемашина",
            self.calib_data["ch_coffee"],
        )
        self.assertEqual(profile.channel_type, ChannelType.WORKING_HOURS)
        # Ночью потребление близко к нулю
        self.assertLess(profile.night_stats.median_power, 0.05)
        # Днем среднее потребление существенно выше
        self.assertGreater(profile.day_stats.mean_power, 0.3)


class TestAnomalyDetector(unittest.TestCase):
    """Тестирование срабатывания трех триггеров и дебаунсинга."""

    def setUp(self):
        self.generator = SyntheticTelemetryGenerator(seed=42)
        self.engine = CalibrationEngine()
        self.start_time = datetime(2026, 11, 1, 0, 0, 0)
        self.calib_data = self.generator.generate_calibration_data(
            start_time=self.start_time,
            days=7,
            sample_step_minutes=1,
        )
        self.profiles = {
            cid: self.engine.calibrate_channel(cid, self.generator.CHANNEL_NAMES[cid], r_list)
            for cid, r_list in self.calib_data.items()
        }
        self.detector = AnomalyDetector(
            profiles=self.profiles,
            night_debounce_minutes=15,
            day_debounce_minutes=10,
        )

    def test_trigger_1_night_overconsumption(self):
        # Подаем ночью на ch_base завышенную мощность (+200% к базе) в течение 20 минут
        base_time = datetime(2026, 11, 8, 2, 0, 0)  # Ночь: 02:00
        anomalies = []
        for i in range(20):
            t = base_time + timedelta(minutes=i)
            r = TelemetryReading(
                timestamp=t,
                channel_id="ch_base",
                voltage=220.0,
                current=2.0,
                power=0.45,  # Норма 0.12 кВт
            )
            res = self.detector.process_reading(r)
            if res:
                anomalies.extend(res)

        # Срабатывание должно произойти на 15-й минуте устойчивого превышения
        self.assertGreaterEqual(len(anomalies), 1)
        ev = anomalies[0]
        self.assertEqual(ev.anomaly_type, AnomalyType.NIGHT_OVERCONSUMPTION)
        self.assertIn("ночное потребление", ev.description)
        self.assertIn("Возможно, забыт включённым прибор", ev.description)

    def test_trigger_1_spike_rejection(self):
        # Кратковременный всплеск на 3 минуты не должен вызывать алерт
        base_time = datetime(2026, 11, 8, 3, 0, 0)
        anomalies = []
        for i in range(3):
            t = base_time + timedelta(minutes=i)
            r = TelemetryReading(
                timestamp=t,
                channel_id="ch_base",
                voltage=220.0,
                current=5.0,
                power=1.1,
            )
            res = self.detector.process_reading(r)
            if res:
                anomalies.extend(res)
        self.assertEqual(len(anomalies), 0)

    def test_trigger_2_cyclicity_breakdown(self):
        # Подаем непрерывную работу компрессора на 120 минут (норма ~25 мин)
        base_time = datetime(2026, 11, 8, 4, 0, 0)
        anomalies = []
        for i in range(120):
            t = base_time + timedelta(minutes=i)
            r = TelemetryReading(
                timestamp=t,
                channel_id="ch_fridge",
                voltage=220.0,
                current=3.9,
                power=0.86,
            )
            res = self.detector.process_reading(r)
            if res:
                anomalies.extend(res)

        self.assertGreaterEqual(len(anomalies), 1)
        ev = anomalies[0]
        self.assertEqual(ev.anomaly_type, AnomalyType.CYCLICITY_BREAKDOWN)
        self.assertIn("работает без остановки", ev.description)
        self.assertIn("Подозрение на поломку", ev.description)

    def test_trigger_3_daytime_overload(self):
        # Днем подаем на кофемашину 4.5 кВт в течение 15 минут
        base_time = datetime(2026, 11, 8, 12, 0, 0)  # День: 12:00
        anomalies = []
        for i in range(15):
            t = base_time + timedelta(minutes=i)
            r = TelemetryReading(
                timestamp=t,
                channel_id="ch_coffee",
                voltage=220.0,
                current=20.0,
                power=4.5,
            )
            res = self.detector.process_reading(r)
            if res:
                anomalies.extend(res)

        self.assertGreaterEqual(len(anomalies), 1)
        ev = anomalies[0]
        self.assertEqual(ev.anomaly_type, AnomalyType.DAYTIME_OVERLOAD)
        self.assertIn("потребление в рабочие часы", ev.description)
        self.assertIn("Нештатный режим или перегрузка", ev.description)


class TestDashboardDataExporter(unittest.TestCase):
    """Тестирование корректности данных для дашборда."""

    def test_summary_table_generation(self):
        generator = SyntheticTelemetryGenerator(seed=42)
        engine = CalibrationEngine()
        calib_data = generator.generate_calibration_data(datetime(2026, 11, 1), days=7)
        profiles = {
            cid: engine.calibrate_channel(cid, generator.CHANNEL_NAMES[cid], r_list)
            for cid, r_list in calib_data.items()
        }
        detector = AnomalyDetector(profiles)
        # Обрабатываем последнее чтение
        for cid in profiles:
            detector.process_reading(calib_data[cid][-1])

        rows = DashboardDataExporter.build_summary_table(detector)
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertIn("channel_id", r)
            self.assertIn("status_badge", r)
            self.assertIn("norm_range_str", r)


if __name__ == "__main__":
    unittest.main()
