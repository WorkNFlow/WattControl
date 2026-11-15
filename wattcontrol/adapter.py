"""Адаптеры данных телеметрии для сервиса «ВаттКонтроль».

Включает:
1. TuyaAdapter — парсинг сырых пакетов Tuya Cloud API (однофазных и трёхфазных).
2. SyntheticTelemetryGenerator — генератор 7-дневной реалистичной телеметрии для калибровки
   и инъекции сценариев аномалий для демонстрации и университетской защиты.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from wattcontrol.models import TelemetryReading


class TuyaAdapter:
    """Адаптер для разбора ответов Tuya Cloud API."""

    @staticmethod
    def parse_payload(
        payload: Union[Dict[str, Any], str],
        timestamp: Optional[datetime] = None,
        default_channel_id: str = "phase_a",
    ) -> List[TelemetryReading]:
        """Разбирает ответ Tuya API в список TelemetryReading.

        Поддерживает как одиночный статус:
        {
          "code": "phase_a",
          "value": "{\"voltage\":217.6,\"electricCurrent\":1.000,\"power\":10.000}"
        }
        так и массив статусов устройства или вложенный объект result:
        {
          "result": [
             {"code": "phase_a", "value": "..."},
             {"code": "energy_daily", "value": "..."}
          ]
        }
        """
        ts = timestamp or datetime.now()
        data = json.loads(payload) if isinstance(payload, str) else payload

        items: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            if "result" in data and isinstance(data["result"], list):
                items = data["result"]
            elif "result" in data and isinstance(data["result"], dict) and "status" in data["result"]:
                items = data["result"]["status"]
            elif "code" in data:
                items = [data]
            elif "status" in data and isinstance(data["status"], list):
                items = data["status"]
            else:
                items = [data]
        elif isinstance(data, list):
            items = data

        readings: List[TelemetryReading] = []
        energy_daily_val: Optional[float] = None

        # Сначала ищем общее значение energy_daily, если оно передано отдельным кодом
        for item in items:
            if not isinstance(item, dict):
                continue
            code = item.get("code")
            if code == "energy_daily":
                val = item.get("value")
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except json.JSONDecodeError:
                        pass
                if isinstance(val, dict) and "electricTotal" in val:
                    energy_daily_val = float(val["electricTotal"])

        # Теперь парсим фазы / каналы
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", default_channel_id))
            if code == "energy_daily":
                continue

            raw_val = item.get("value")
            if raw_val is None:
                continue

            parsed_val: Dict[str, Any] = {}
            if isinstance(raw_val, str):
                try:
                    parsed_val = json.loads(raw_val)
                except json.JSONDecodeError:
                    continue
            elif isinstance(raw_val, dict):
                parsed_val = raw_val

            # Читаем voltage, electricCurrent, power
            # По документации Tuya:
            # voltage: В (например 220.0 или 217.6)
            # electricCurrent: А (например 1.000)
            # power: кВт (например 0.850 или 10.000)
            voltage = float(parsed_val.get("voltage", 220.0))
            current = float(parsed_val.get("electricCurrent", parsed_val.get("current", 0.0)))
            power = float(parsed_val.get("power", 0.0))

            readings.append(
                TelemetryReading(
                    timestamp=ts,
                    channel_id=code,
                    voltage=voltage,
                    current=current,
                    power=power,
                    energy_daily=energy_daily_val,
                )
            )

        return readings


class SyntheticTelemetryGenerator:
    """Генератор синтетических временных рядов энергопотребления для кофейни.

    Моделирует 3 характерных канала:
    1. ch_fridge — Холодильная витрина с молочной продукцией (циклы 25 мин ON / 20 мин OFF).
    2. ch_coffee — Кофемашина и рожковая группа (рабочие часы 08:00 - 21:00, пики до 3.2 кВт).
    3. ch_base   — Дежурная сеть 24/7 (роутер, касса, видеонаблюдение ~ 0.12 кВт).
    """

    CHANNEL_NAMES = {
        "ch_fridge": "Холодильная витрина (молочка)",
        "ch_coffee": "Кофемашина и гриль",
        "ch_base": "Дежурная сеть 24/7 (роутер, касса)",
    }

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def generate_calibration_data(
        self,
        start_time: datetime,
        days: int = 7,
        sample_step_minutes: int = 1,
    ) -> Dict[str, List[TelemetryReading]]:
        """Генерирует 7 дней нормальной телеметрии (10 080 точек на канал)."""
        readings_by_channel: Dict[str, List[TelemetryReading]] = {
            "ch_fridge": [],
            "ch_coffee": [],
            "ch_base": [],
        }

        total_minutes = days * 24 * 60
        total_steps = total_minutes // sample_step_minutes

        # Внутреннее состояние циклического компрессора
        # Цикл: 25 мин ON (0.85 кВт), 20 мин OFF (0.015 кВт)
        fridge_on = True
        fridge_timer = 0
        current_cycle_target = 25

        for step in range(total_steps):
            current_time = start_time + timedelta(minutes=step * sample_step_minutes)
            hour = current_time.hour
            minute = current_time.minute
            is_night = hour < 7 or hour >= 23
            is_open = 8 <= hour < 21

            # -------------------------------------------------------------
            # Канал 1: Холодильная витрина (CYCLIC)
            # -------------------------------------------------------------
            fridge_timer += sample_step_minutes
            if fridge_on and fridge_timer >= current_cycle_target:
                fridge_on = False
                fridge_timer = 0
                # Длительность фазы OFF: 18..22 мин
                current_cycle_target = self.rng.randint(18, 22)
            elif (not fridge_on) and fridge_timer >= current_cycle_target:
                fridge_on = True
                fridge_timer = 0
                # Днем чаще открывают дверцы, компрессор работает чуть дольше (24..28 мин), ночью (20..24 мин)
                current_cycle_target = self.rng.randint(24, 28) if is_open else self.rng.randint(20, 24)

            voltage_base = 220.0 + math.sin(step / 100.0) * 3.0 + self.rng.gauss(0, 1.0)
            if fridge_on:
                fridge_power = 0.85 + self.rng.gauss(0, 0.02)
                fridge_current = (fridge_power * 1000.0) / voltage_base
            else:
                fridge_power = 0.015 + abs(self.rng.gauss(0, 0.002))
                fridge_current = (fridge_power * 1000.0) / voltage_base

            readings_by_channel["ch_fridge"].append(
                TelemetryReading(
                    timestamp=current_time,
                    channel_id="ch_fridge",
                    voltage=voltage_base,
                    current=max(0.01, fridge_current),
                    power=max(0.01, fridge_power),
                )
            )

            # -------------------------------------------------------------
            # Канал 2: Кофемашина и гриль (WORKING_HOURS)
            # -------------------------------------------------------------
            if is_open:
                # Базовый подогрев бойлера ~0.4 кВт, периодические проливы/приготовления кофе (1.8..3.2 кВт)
                # Пики приходятся на утренний (08:30-10:30) и обеденный (13:00-14:30) часы
                rush_hour = (8 <= hour <= 10) or (13 <= hour <= 14)
                brewing_chance = 0.45 if rush_hour else 0.20
                if self.rng.random() < brewing_chance:
                    coffee_power = self.rng.uniform(1.8, 3.1)
                else:
                    coffee_power = 0.38 + self.rng.gauss(0, 0.04)
            else:
                # Ночью прибор выключен, дежурный режим индикации 0.005 кВт
                coffee_power = 0.005 + abs(self.rng.gauss(0, 0.001))

            coffee_current = (coffee_power * 1000.0) / voltage_base
            readings_by_channel["ch_coffee"].append(
                TelemetryReading(
                    timestamp=current_time,
                    channel_id="ch_coffee",
                    voltage=voltage_base,
                    current=max(0.01, coffee_current),
                    power=max(0.005, coffee_power),
                )
            )

            # -------------------------------------------------------------
            # Канал 3: Дежурная сеть 24/7 (BASE_24_7)
            # -------------------------------------------------------------
            # Роутер + касса + видеонаблюдение: почти константа 0.12 кВт
            base_power = 0.120 + self.rng.gauss(0, 0.005)
            base_current = (base_power * 1000.0) / voltage_base
            readings_by_channel["ch_base"].append(
                TelemetryReading(
                    timestamp=current_time,
                    channel_id="ch_base",
                    voltage=voltage_base,
                    current=max(0.05, base_current),
                    power=max(0.05, base_power),
                )
            )

        return readings_by_channel

    def generate_day8_with_anomalies(
        self,
        day8_start: datetime,
        sample_step_minutes: int = 1,
    ) -> Dict[str, List[TelemetryReading]]:
        """Генерирует 8-й день с 3 целевыми инцидентами для проверки триггеров:

        1. ch_base: с 01:00 до 05:00 забыт включенным обогреватель/дежурный свет (+0.45 кВт, +375% к базе).
           -> Триггер 1: Завышенная ночная база.
        2. ch_fridge: с 02:30 до 06:30 компрессор работает без остановки 4 часа (утечка хладагента/открытая дверь).
           -> Триггер 2: Нарушение цикличности.
        3. ch_coffee: с 12:00 до 13:00 перегрузка рожковой группы / залипание ТЭНа (4.5 кВт, +50% выше нормы).
           -> Триггер 3: Отклонение в рабочие часы.
        """
        day8_readings = self.generate_calibration_data(
            start_time=day8_start,
            days=1,
            sample_step_minutes=sample_step_minutes,
        )

        # Инъекция 1: Завышенная ночная база на ch_base (01:00 - 05:00)
        for r in day8_readings["ch_base"]:
            if 1 <= r.timestamp.hour < 5:
                # Добавляем 0.35 кВт (итого ~0.47 кВт, что почти в 4 раза выше нормы 0.12 кВт)
                r.power += 0.35 + self.rng.gauss(0, 0.01)
                r.current = (r.power * 1000.0) / r.voltage

        # Инъекция 2: Нарушение цикличности на ch_fridge (02:30 - 06:30 непрерывная работа компрессора)
        for r in day8_readings["ch_fridge"]:
            h = r.timestamp.hour
            m = r.timestamp.minute
            in_anomaly_window = (h == 2 and m >= 30) or (3 <= h < 6) or (h == 6 and m <= 30)
            if in_anomaly_window:
                # Компрессор не отключается!
                r.power = 0.88 + self.rng.gauss(0, 0.02)
                r.current = (r.power * 1000.0) / r.voltage

        # Инъекция 3: Дневной перегруз на ch_coffee (12:00 - 13:00)
        for r in day8_readings["ch_coffee"]:
            if 12 <= r.timestamp.hour < 13:
                r.power = 4.45 + self.rng.gauss(0, 0.1)
                r.current = (r.power * 1000.0) / r.voltage

        return day8_readings
