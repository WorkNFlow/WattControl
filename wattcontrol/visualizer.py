"""Генератор автономного интерактивного веб-дашборда «ВаттКонтроль».

Создает автономный HTML-файл с двумя экранами:
1. Экран 1: Сводная таблица по всем каналам (статусы 🟢 / 🔴, текущие кВт/А/В, визуальная шкала нагрузки, описание аномалии).
   Поддерживает переключение срезов времени: Ночной инцидент (03:30) / Дневной перегруз (12:30) / Итоги суток (23:59).
2. Экран 2: Интерактивный векторный график (SVG) с коридором нормы (медиана ± std), перекрестьем мыши,
   фильтрами диапазонов и анимированными маркерами сбоев.
Работает полностью офлайн без внешних CDN и зависимостей на базе чистого SVG и современного JS/CSS.
"""

from __future__ import annotations

import json
from typing import Any, Dict


class HTMLDashboardGenerator:
    """Генератор автономного HTML-дашборда."""

    @staticmethod
    def generate_html(dashboard_data: Dict[str, Any], output_path: str) -> None:
        """Формирует и сохраняет автономный HTML-файл дашборда."""
        data_json = json.dumps(dashboard_data, ensure_ascii=False)

        html_template = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark">
  <title>ВаттКонтроль — Система энергомониторинга и детекции аномалий</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #090d16;
      --bg-surface: #0f172a;
      --card-bg: rgba(17, 24, 39, 0.78);
      --card-hover: rgba(30, 41, 59, 0.85);
      --border: rgba(255, 255, 255, 0.08);
      --border-accent: rgba(56, 189, 248, 0.3);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.25);
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.15);
      --danger: #f43f5e;
      --danger-bg: rgba(244, 63, 94, 0.16);
      --warning: #f59e0b;
      --warning-bg: rgba(245, 158, 11, 0.15);
      --corridor-fill: rgba(56, 189, 248, 0.12);
      --corridor-stroke: rgba(56, 189, 248, 0.4);
      --font-sans: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, "SF Mono", "Cascadia Code", "Fira Code", Menlo, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: var(--font-sans);
      background-color: var(--bg);
      background-image: 
        radial-gradient(1200px 600px at 50% -120px, rgba(14, 165, 233, 0.15), transparent 70%),
        radial-gradient(800px 400px at 90% 400px, rgba(99, 102, 241, 0.08), transparent 60%);
      background-attachment: fixed;
      color: var(--text);
      line-height: 1.5;
      padding: 24px 20px 48px;
      min-height: 100vh;
      accent-color: var(--primary);
      scrollbar-color: rgba(148, 163, 184, 0.3) transparent;
    }

    .container {
      max-width: 1260px;
      margin: 0 auto;
    }

    /* Верхняя шапка */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
      flex-wrap: wrap;
      gap: 16px;
    }

    .brand-wrap {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .brand-logo-icon {
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, rgba(14, 165, 233, 0.25), rgba(99, 102, 241, 0.25));
      border: 1px solid rgba(56, 189, 248, 0.4);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 20px rgba(56, 189, 248, 0.2);
    }

    .brand-logo-icon svg {
      width: 24px;
      height: 24px;
      color: var(--primary);
    }

    .brand-text h1 {
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.02em;
      background: linear-gradient(90deg, #ffffff 0%, #38bdf8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .brand-text p {
      color: var(--text-muted);
      font-size: 13px;
      margin-top: 2px;
    }

    .header-badges {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .badge-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid var(--border);
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-muted);
    }

    .badge-chip strong {
      color: var(--text);
    }

    .live-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 10px var(--success);
      animation: pulse-dot 2s infinite;
    }

    @keyframes pulse-dot {
      0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
      70% { transform: scale(1.1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
      100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* Сетка KPI карточек */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
      content-visibility: auto;
      contain-intrinsic-size: auto 120px;
    }

    .kpi-card {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px 20px;
      position: relative;
      overflow: hidden;
      transition: border-color 0.2s, transform 0.2s;
    }

    .kpi-card:hover {
      border-color: rgba(255, 255, 255, 0.16);
      transform: translateY(-1px);
    }

    .kpi-card::before {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, transparent, var(--card-accent, var(--primary)), transparent);
      opacity: 0.8;
    }

    .kpi-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }

    .kpi-title {
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }

    .kpi-icon {
      width: 28px;
      height: 28px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.05);
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--primary);
    }

    .kpi-value {
      font-size: 26px;
      font-weight: 700;
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
      color: #ffffff;
      line-height: 1.2;
    }

    .kpi-subtext {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 6px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .progress-bar-wrap {
      width: 100%;
      height: 6px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 3px;
      margin-top: 10px;
      overflow: hidden;
    }

    .progress-bar-fill {
      height: 100%;
      border-radius: 3px;
      background: var(--primary);
      transition: width 0.4s ease, background-color 0.3s;
    }

    /* Карточки основных экранов */
    .card {
      background: var(--card-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
      content-visibility: auto;
      contain-intrinsic-size: auto 400px;
    }

    @supports not (content-visibility: auto) {
      .card { contain: layout style paint; }
    }

    .card-title-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
      flex-wrap: wrap;
      gap: 12px;
    }

    .card-title-bar h2 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.01em;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .card-subtitle {
      font-size: 12px;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.04);
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }

    /* Панель демонстрационных срезов (Timeline Scrubber) */
    .timeline-controller {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px 18px;
      margin-bottom: 20px;
    }

    .timeline-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      font-size: 13px;
    }

    .timeline-title {
      font-weight: 600;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .timeline-segmented {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }

    @media (max-width: 768px) {
      .timeline-segmented {
        grid-template-columns: 1fr;
      }
    }

    .snapshot-btn {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 10px 14px;
      border-radius: 10px;
      cursor: pointer;
      text-align: left;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      flex-direction: column;
      gap: 4px;
      position: relative;
    }

    .snapshot-btn:hover:not(.active) {
      background: rgba(255, 255, 255, 0.06);
      border-color: rgba(255, 255, 255, 0.15);
      color: var(--text);
    }

    .snapshot-btn.active {
      background: rgba(244, 63, 94, 0.14);
      border-color: var(--danger);
      box-shadow: 0 0 15px rgba(244, 63, 94, 0.2);
    }

    .snapshot-btn.active.normal-mode {
      background: rgba(16, 185, 129, 0.14);
      border-color: var(--success);
      box-shadow: 0 0 15px rgba(16, 185, 129, 0.2);
    }

    .snap-btn-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: 600;
      font-size: 13px;
    }

    .snapshot-btn.active .snap-btn-top {
      color: #fca5a5;
    }

    .snapshot-btn.active.normal-mode .snap-btn-top {
      color: #86efac;
    }

    .snap-btn-desc {
      font-size: 11px;
      color: var(--text-dim);
      line-height: 1.3;
    }

    .snapshot-btn.active .snap-btn-desc {
      color: var(--text-muted);
    }

    .scenario-banner {
      margin-top: 12px;
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 12px;
      line-height: 1.45;
      display: flex;
      align-items: flex-start;
      gap: 10px;
      border: 1px solid var(--border);
      background: rgba(15, 23, 42, 0.5);
    }

    .scenario-banner.alert {
      background: rgba(244, 63, 94, 0.08);
      border-color: rgba(244, 63, 94, 0.3);
      color: #fecdd3;
    }

    .scenario-banner.normal {
      background: rgba(16, 185, 129, 0.08);
      border-color: rgba(16, 185, 129, 0.3);
      color: #a7f3d0;
    }

    /* Таблица сводного мониторинга */
    .table-container {
      width: 100%;
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(15, 23, 42, 0.4);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }

    th {
      color: var(--text-muted);
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 14px 16px;
      background: rgba(15, 23, 42, 0.8);
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }

    td {
      padding: 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      vertical-align: middle;
      transition: background-color 0.15s;
    }

    tr:last-child td {
      border-bottom: none;
    }

    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }

    .channel-cell {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .channel-icon-wrap {
      width: 38px;
      height: 38px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border);
      font-size: 18px;
      flex-shrink: 0;
    }

    .channel-info h4 {
      font-size: 14px;
      font-weight: 600;
      color: #ffffff;
      margin-bottom: 2px;
    }

    .channel-info span {
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-dim);
    }

    .type-pill {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      background: rgba(148, 163, 184, 0.1);
      color: var(--text-muted);
      border: 1px solid rgba(148, 163, 184, 0.2);
      white-space: nowrap;
    }

    .power-metric {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 140px;
    }

    .power-main {
      font-family: var(--font-mono);
      font-size: 15px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      color: #ffffff;
    }

    .power-sub {
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-dim);
    }

    .load-gauge {
      width: 100%;
      height: 4px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 2px;
      overflow: hidden;
      margin-top: 4px;
    }

    .load-gauge-bar {
      height: 100%;
      border-radius: 2px;
      background: var(--primary);
      transition: width 0.3s;
    }

    .load-gauge-bar.danger {
      background: var(--danger);
    }

    .norm-box {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--text-muted);
      white-space: nowrap;
    }

    .norm-box strong {
      color: var(--primary);
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 12px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }

    .status-normal {
      background: var(--success-bg);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }

    .status-anomaly {
      background: var(--danger-bg);
      color: #f87171;
      border: 1px solid rgba(244, 63, 94, 0.4);
      animation: alert-pulse 2s infinite;
    }

    @keyframes alert-pulse {
      0% { box-shadow: 0 0 0 0 rgba(244, 63, 94, 0.4); }
      70% { box-shadow: 0 0 0 8px rgba(244, 63, 94, 0); }
      100% { box-shadow: 0 0 0 0 rgba(244, 63, 94, 0); }
    }

    .incident-diag {
      font-size: 12px;
      line-height: 1.45;
      color: var(--text-muted);
      max-width: 360px;
    }

    .incident-diag.alert {
      color: #fca5a5;
    }

    /* Вкладки каналов графика */
    .tabs-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
      gap: 12px;
    }

    .tabs-group {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .tab-btn {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 8px 16px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

    .tab-btn:hover:not(.active) {
      background: rgba(255, 255, 255, 0.06);
      color: var(--text);
    }

    .tab-btn.active {
      background: rgba(56, 189, 248, 0.15);
      border-color: var(--primary);
      color: #ffffff;
      font-weight: 600;
      box-shadow: 0 0 15px rgba(56, 189, 248, 0.2);
    }

    .tab-status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--success);
    }

    .tab-status-dot.danger {
      background: var(--danger);
      box-shadow: 0 0 6px var(--danger);
    }

    /* Фильтры диапазона времени */
    .range-group {
      display: flex;
      gap: 4px;
      background: rgba(15, 23, 42, 0.6);
      padding: 3px;
      border-radius: 8px;
      border: 1px solid var(--border);
    }

    .range-btn {
      background: transparent;
      border: none;
      color: var(--text-dim);
      font-size: 11px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }

    .range-btn:hover:not(.active) {
      color: var(--text);
    }

    .range-btn.active {
      background: rgba(255, 255, 255, 0.1);
      color: #ffffff;
    }

    /* Область графика */
    .chart-wrapper {
      position: relative;
      width: 100%;
      height: 380px;
      background: rgba(15, 23, 42, 0.4);
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 10px;
      user-select: none;
    }

    svg.chart-svg {
      width: 100%;
      height: 100%;
      overflow: visible;
      display: block;
    }

    /* Тултип графика */
    .chart-hud-tooltip {
      position: absolute;
      background: rgba(15, 23, 42, 0.92);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(56, 189, 248, 0.4);
      border-radius: 10px;
      padding: 12px 16px;
      font-size: 12px;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.1s ease, transform 0.1s ease;
      box-shadow: 0 15px 30px -5px rgba(0, 0, 0, 0.8), 0 0 20px rgba(56, 189, 248, 0.15);
      z-index: 50;
      min-width: 200px;
      transform: translate(-50%, -115%);
    }

    .hud-time {
      font-weight: 700;
      font-size: 13px;
      color: #ffffff;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      padding-bottom: 6px;
      margin-bottom: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .hud-row {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 4px;
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }

    .hud-label {
      color: var(--text-muted);
    }

    .hud-val {
      font-weight: 600;
      color: #ffffff;
    }

    .hud-val.actual {
      color: var(--primary);
    }

    .hud-val.alert {
      color: #f87171;
    }

    /* Легенда */
    .legend-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 16px;
      flex-wrap: wrap;
      gap: 16px;
      font-size: 12px;
      color: var(--text-muted);
      padding: 10px 14px;
      background: rgba(15, 23, 42, 0.4);
      border-radius: 10px;
      border: 1px solid var(--border);
    }

    .legend-items {
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .leg-swatch-line {
      width: 18px;
      height: 3px;
      border-radius: 2px;
      background: var(--primary);
    }

    .leg-swatch-corridor {
      width: 18px;
      height: 10px;
      border-radius: 3px;
      background: var(--corridor-fill);
      border: 1px dashed var(--primary);
    }

    .leg-swatch-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--danger);
      box-shadow: 0 0 6px var(--danger);
    }

    /* Профиль калибровки канала под графиком */
    .profile-drawer {
      margin-top: 16px;
      padding: 14px 18px;
      background: rgba(15, 23, 42, 0.5);
      border-radius: 10px;
      border: 1px solid var(--border);
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      font-size: 12px;
    }

    .profile-item-title {
      color: var(--text-dim);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 11px;
      margin-bottom: 2px;
    }

    .profile-item-value {
      color: var(--text);
      font-family: var(--font-mono);
      font-weight: 600;
    }

    /* Хроника всех сработавших алертов дня */
    .alerts-feed {
      margin-top: 20px;
      border-top: 1px solid var(--border);
      padding-top: 18px;
    }

    .alerts-feed-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .alert-cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 12px;
    }

    .alert-card-item {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border);
      border-left: 3px solid var(--danger);
      border-radius: 8px;
      padding: 12px 14px;
      font-size: 12px;
      line-height: 1.4;
    }

    .alert-card-item.resolved {
      border-left-color: var(--success);
    }

    .alert-card-item-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
      font-weight: 600;
    }

    .alert-card-time {
      font-family: var(--font-mono);
      color: var(--primary);
    }

    /* Анимация маркеров */
    .anomaly-ping {
      animation: ping-marker 2s infinite ease-out;
      transform-origin: center;
    }

    @keyframes ping-marker {
      0% { r: 6; opacity: 1; }
      100% { r: 16; opacity: 0; }
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- ВЕРХНЯЯ ШАПКА -->
    <header>
      <div class="brand-wrap">
        <div class="brand-logo-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
          </svg>
        </div>
        <div class="brand-text">
          <h1>ВАТТКОНТРОЛЬ</h1>
          <p>Чистая статистика без нейросетей: 7 дней автокалибровки индивидуальной нормы и потоковый мониторинг</p>
        </div>
      </div>
      <div class="header-badges">
        <div class="badge-chip">
          <div class="live-dot"></div>
          <span>Система онлайн • Опрос <strong>1 раз/мин</strong></span>
        </div>
        <div class="badge-chip">
          <span>☕ <strong>«Эспрессо Бар»</strong> • Wi-Fi 3-Ch Tuya</span>
        </div>
      </div>
    </header>

    <!-- KPI КАРТОЧКИ ОБЗОРА -->
    <div class="kpi-grid">
      <div class="kpi-card" style="--card-accent: var(--primary);">
        <div class="kpi-header">
          <span class="kpi-title">Суммарная нагрузка</span>
          <div class="kpi-icon">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>
            </svg>
          </div>
        </div>
        <div class="kpi-value" id="kpiTotalPower">0.00 кВт</div>
        <div class="kpi-subtext" id="kpiPowerLimit">Из 15.0 кВт лимита ввода</div>
        <div class="progress-bar-wrap">
          <div class="progress-bar-fill" id="kpiPowerBar" style="width: 10%;"></div>
        </div>
      </div>

      <div class="kpi-card" id="kpiStatusCard" style="--card-accent: var(--danger);">
        <div class="kpi-header">
          <span class="kpi-title">Статус оборудования</span>
          <div class="kpi-icon">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
          </div>
        </div>
        <div class="kpi-value" id="kpiActiveAlerts" style="color: var(--danger);">2 инцидента</div>
        <div class="kpi-subtext" id="kpiStatusSubtext">Требуется вмешательство персонала</div>
      </div>

      <div class="kpi-card" style="--card-accent: #8b5cf6;">
        <div class="kpi-header">
          <span class="kpi-title">Дежурная база</span>
          <div class="kpi-icon">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
              <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
              <line x1="6" y1="6" x2="6.01" y2="6"></line>
              <line x1="6" y1="18" x2="6.01" y2="18"></line>
            </svg>
          </div>
        </div>
        <div class="kpi-value">0.120 кВт</div>
        <div class="kpi-subtext">Норма ночного фона (касса, Wi-Fi)</div>
      </div>

      <div class="kpi-card" style="--card-accent: var(--success);">
        <div class="kpi-header">
          <span class="kpi-title">Калибровка профиля</span>
          <div class="kpi-icon">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
              <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
          </div>
        </div>
        <div class="kpi-value">10 080 точек</div>
        <div class="kpi-subtext">7 дней калибровки • Медиана ± 1σ</div>
      </div>
    </div>

    <!-- ЭКРАН 1: СВОДНАЯ ТАБЛИЦА С ВЫБОРОМ СРЕЗА -->
    <div class="card">
      <div class="card-title-bar">
        <h2>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="3" y1="9" x2="21" y2="9"></line>
            <line x1="9" y1="21" x2="9" y2="9"></line>
          </svg>
          Экран 1: Сводный мониторинг каналов
        </h2>
        <span class="card-subtitle">
          Только физические величины (кВт, А, В) • Без рублевых тарифов
        </span>
      </div>

      <!-- Переключатель демонстрационных срезов времени -->
      <div class="timeline-controller">
        <div class="timeline-header">
          <span class="timeline-title">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            Демонстрация инцидентов во времени (срезы мониторинга 8-го дня):
          </span>
          <span style="font-size: 11px; color: var(--text-dim);">Выберите момент для инспекции статусов</span>
        </div>

        <div class="timeline-segmented">
          <button class="snapshot-btn active" id="btnSnapNight" onclick="setSnapshot('night_incident')">
            <div class="snap-btn-top">
              <span>🔴 03:30 Ночной инцидент</span>
              <span class="status-badge status-anomaly" style="padding: 2px 8px; font-size: 10px;">2 аварии</span>
            </div>
            <div class="snap-btn-desc">Непрерывная работа холодильника + забытый прибор на дежурной сети</div>
          </button>

          <button class="snapshot-btn" id="btnSnapDay" onclick="setSnapshot('day_incident')">
            <div class="snap-btn-top">
              <span>🔴 12:30 Дневной инцидент</span>
              <span class="status-badge status-anomaly" style="padding: 2px 8px; font-size: 10px;">1 авария</span>
            </div>
            <div class="snap-btn-desc">Аномальный перегруз линии кофемашины и гриля (> 4.4 кВт)</div>
          </button>

          <button class="snapshot-btn normal-mode" id="btnSnapEnd" onclick="setSnapshot('end_of_day')">
            <div class="snap-btn-top">
              <span>🟢 23:59 Итоги суток</span>
              <span class="status-badge status-normal" style="padding: 2px 8px; font-size: 10px;">Норма</span>
            </div>
            <div class="snap-btn-desc">Нормализация всех каналов, завершение всех активных инцидентов</div>
          </button>
        </div>

        <!-- Контекстный баннер описания ситуации -->
        <div class="scenario-banner alert" id="scenarioBanner">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0; margin-top:2px;">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <div id="scenarioText">
            <strong>Срез 03:30 (Ночь):</strong> Зафиксировано 2 одновременных сбоя: компрессор холодильной витрины работает 1.4 ч без остановки (норма отключения: каждые 24 мин), а на дежурной линии роутера обнаружено превышение нормы на 294% (вероятно, оставлен включенным конвектор или подсветка).
          </div>
        </div>
      </div>

      <!-- Таблица -->
      <div class="table-container">
        <table id="summaryTable">
          <thead>
            <tr>
              <th>Канал оборудования</th>
              <th>Тип нагрузки</th>
              <th>Текущая мощность и фаза</th>
              <th>Индивидуальная норма</th>
              <th>Статус</th>
              <th>Диагностика и инцидент</th>
            </tr>
          </thead>
          <tbody id="summaryTableBody">
          </tbody>
        </table>
      </div>
    </div>

    <!-- ЭКРАН 2: ИНТЕРАКТИВНЫЙ ГРАФИК -->
    <div class="card">
      <div class="card-title-bar">
        <h2>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
          </svg>
          Экран 2: График расхода с коридором нормы (Медиана ± 1σ)
        </h2>
        <span class="card-subtitle">
          Поминутная детализация (1 440 точек) • Векторная отрисовка SVG
        </span>
      </div>

      <!-- Вкладки каналов и временные диапазоны -->
      <div class="tabs-bar">
        <div class="tabs-group" id="channelTabs"></div>
        <div class="range-group">
          <button class="range-btn active" onclick="setChartRange('all')">24 часа</button>
          <button class="range-btn" onclick="setChartRange('night')">Ночь (00-06)</button>
          <button class="range-btn" onclick="setChartRange('day')">День (06-18)</button>
          <button class="range-btn" onclick="setChartRange('evening')">Вечер (18-24)</button>
        </div>
      </div>

      <!-- Холст SVG Графика -->
      <div class="chart-wrapper" id="chartWrapper">
        <svg class="chart-svg" id="chartSvg"></svg>
        <div class="chart-hud-tooltip" id="chartHud"></div>
      </div>

      <!-- Легенда -->
      <div class="legend-row">
        <div class="legend-items">
          <div class="legend-item">
            <div class="leg-swatch-line"></div>
            <span>Факт мощности (кВт)</span>
          </div>
          <div class="legend-item">
            <div class="leg-swatch-corridor"></div>
            <span>Коридор нормы (Медиана ± 1σ)</span>
          </div>
          <div class="legend-item">
            <div style="width: 18px; height: 1px; border-top: 2px dotted #94a3b8;"></div>
            <span>Медиана нормы</span>
          </div>
          <div class="legend-item">
            <div class="leg-swatch-dot"></div>
            <span>Точка срабатывания аномалии</span>
          </div>
        </div>
        <div style="font-size: 11px; color: var(--text-dim);">
          Наведите курсор на график для инспекции поминутных значений
        </div>
      </div>

      <!-- Блок калиброванного профиля канала -->
      <div class="profile-drawer" id="channelProfileDrawer">
      </div>

      <!-- Хроника всех сработавших алертов дня -->
      <div class="alerts-feed">
        <div class="alerts-feed-title">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          Хроника зафиксированных инцидентов 8-го дня (3 подтвержденных сценария):
        </div>
        <div class="alert-cards-grid" id="alertsHistoryGrid"></div>
      </div>
    </div>
  </div>

  <script>
    const rawData = __DATA_JSON__;
    let activeChannelId = Object.keys(rawData.charts)[0];
    let currentSnapshotKey = "night_incident";
    let currentRangePreset = "all";

    const channelIcons = {
      "ch_fridge": "❄️",
      "ch_coffee": "☕",
      "ch_base": "🔌"
    };

    const scenarioDescriptions = {
      "night_incident": {
        type: "alert",
        html: "<strong>Срез 03:30 (Ночной инцидент):</strong> Активно 2 сбоя! Канал <em>Холодильная витрина</em> работает непрерывно уже 1.4 ч (превышен предел в 53 мин, подозрение на утечку хладагента). На линии <em>Дежурная сеть 24/7</em> ночной фон вырос на +294% (0.47 кВт вместо нормы 0.12 кВт — оставлен включенным прибор)."
      },
      "day_incident": {
        type: "alert",
        html: "<strong>Срез 12:30 (Дневной инцидент):</strong> Пиковая перегрузка на линии <em>Кофемашина и гриль</em>! Мощность достигла 4.48 кВт (+1064% выше нормы 0.38 кВт). Ночной инцидент холодильника благополучно завершился после разморозки в 04:36."
      },
      "end_of_day": {
        type: "normal",
        html: "<strong>Срез 23:59 (Итоги суток):</strong> Все каналы вернулись в калиброванный коридор нормы. Инциденты устранены персоналом, дежурная сеть вернулась к эталонному фону 0.11 кВт, компрессор витрины снова отключается каждые 20 минут."
      }
    };

    // Переключение демонстрационного среза
    function setSnapshot(key) {
      currentSnapshotKey = key;
      document.querySelectorAll(".snapshot-btn").forEach(btn => btn.classList.remove("active"));
      if (key === "night_incident") document.getElementById("btnSnapNight").classList.add("active");
      if (key === "day_incident") document.getElementById("btnSnapDay").classList.add("active");
      if (key === "end_of_day") document.getElementById("btnSnapEnd").classList.add("active");

      // Обновление баннера описания
      const scInfo = scenarioDescriptions[key] || scenarioDescriptions["night_incident"];
      const banner = document.getElementById("scenarioBanner");
      banner.className = `scenario-banner ${scInfo.type}`;
      document.getElementById("scenarioText").innerHTML = scInfo.html;

      renderKPI();
      renderTable();
      renderTabs();
    }

    // Рендер верхних KPI
    function renderKPI() {
      const rows = (rawData.snapshots && rawData.snapshots[currentSnapshotKey]) 
                    ? rawData.snapshots[currentSnapshotKey] 
                    : rawData.summary_table;

      let totalPower = 0;
      let anomalyCount = 0;

      rows.forEach(r => {
        totalPower += (r.current_power_kw || 0);
        if (r.status_code === "ANOMALY") anomalyCount++;
      });

      document.getElementById("kpiTotalPower").textContent = totalPower.toFixed(2) + " кВт";
      const pct = Math.min(100, Math.round((totalPower / 15.0) * 100));
      const pBar = document.getElementById("kpiPowerBar");
      pBar.style.width = pct + "%";
      pBar.style.backgroundColor = pct > 70 ? "var(--danger)" : pct > 40 ? "var(--warning)" : "var(--primary)";
      document.getElementById("kpiPowerLimit").textContent = `${pct}% от лимита ввода 15 кВт`;

      const kpiStatusCard = document.getElementById("kpiStatusCard");
      const kpiActiveAlerts = document.getElementById("kpiActiveAlerts");
      const kpiStatusSubtext = document.getElementById("kpiStatusSubtext");

      if (anomalyCount > 0) {
        kpiStatusCard.style.setProperty("--card-accent", "var(--danger)");
        kpiActiveAlerts.textContent = `${anomalyCount} ${anomalyCount === 1 ? 'инцидент' : 'инцидента'}`;
        kpiActiveAlerts.style.color = "var(--danger)";
        kpiStatusSubtext.textContent = "Требуется вмешательство оператора";
      } else {
        kpiStatusCard.style.setProperty("--card-accent", "var(--success)");
        kpiActiveAlerts.textContent = "В норме";
        kpiActiveAlerts.style.color = "var(--success)";
        kpiStatusSubtext.textContent = "Все 3 канала в пределах коридора";
      }
    }

    // Отрисовка таблицы сводного мониторинга
    function renderTable() {
      const tbody = document.getElementById("summaryTableBody");
      tbody.innerHTML = "";

      const rows = (rawData.snapshots && rawData.snapshots[currentSnapshotKey]) 
                    ? rawData.snapshots[currentSnapshotKey] 
                    : rawData.summary_table;

      rows.forEach(row => {
        const tr = document.createElement("tr");
        const isAnomaly = row.status_code === "ANOMALY";
        const badgeClass = isAnomaly ? "status-anomaly" : "status-normal";
        const icon = channelIcons[row.channel_id] || "⚡";

        // Расчет заполнения шкалы
        const pVal = row.current_power_kw || 0;
        let gaugePct = 30;
        if (row.channel_id === "ch_coffee") gaugePct = Math.min(100, (pVal / 4.5) * 100);
        else if (row.channel_id === "ch_fridge") gaugePct = Math.min(100, (pVal / 1.0) * 100);
        else gaugePct = Math.min(100, (pVal / 0.5) * 100);

        tr.innerHTML = `
          <td>
            <div class="channel-cell">
              <div class="channel-icon-wrap">${icon}</div>
              <div class="channel-info">
                <h4>${row.channel_name}</h4>
                <span>ID: ${row.channel_id}</span>
              </div>
            </div>
          </td>
          <td>
            <span class="type-pill">${row.channel_type_label}</span>
          </td>
          <td>
            <div class="power-metric">
              <div class="power-main">${row.current_power_kw.toFixed(3)} кВт</div>
              <div class="power-sub">${row.current_current_a.toFixed(2)} А • ${row.current_voltage_v} В</div>
              <div class="load-gauge">
                <div class="load-gauge-bar ${isAnomaly ? 'danger' : ''}" style="width: ${gaugePct}%;"></div>
              </div>
            </div>
          </td>
          <td>
            <div class="norm-box">
              ${row.norm_range_str}
            </div>
          </td>
          <td>
            <span class="status-badge ${badgeClass}">
              ${isAnomaly ? '🔴 Отклонение' : '🟢 В норме'}
            </span>
          </td>
          <td>
            <div class="incident-diag ${isAnomaly ? 'alert' : ''}">
              ${row.last_anomaly_description}
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Вкладки переключения каналов графика
    function renderTabs() {
      const container = document.getElementById("channelTabs");
      container.innerHTML = "";

      const currentRows = (rawData.snapshots && rawData.snapshots[currentSnapshotKey]) 
                           ? rawData.snapshots[currentSnapshotKey] 
                           : rawData.summary_table;

      const channelStatusMap = {};
      currentRows.forEach(r => {
        channelStatusMap[r.channel_id] = r.status_code === "ANOMALY";
      });

      Object.keys(rawData.charts).forEach(cid => {
        const ch = rawData.charts[cid];
        const isAlert = channelStatusMap[cid];
        const icon = channelIcons[cid] || "⚡";

        const btn = document.createElement("button");
        btn.className = `tab-btn ${cid === activeChannelId ? 'active' : ''}`;
        btn.innerHTML = `
          <span>${icon}</span>
          <span>${ch.channel_name}</span>
          <span class="tab-status-dot ${isAlert ? 'danger' : ''}"></span>
        `;
        btn.onclick = () => {
          activeChannelId = cid;
          renderTabs();
          renderChart();
          renderProfileDrawer();
        };
        container.appendChild(btn);
      });
    }

    // Фильтр диапазона времени графика
    function setChartRange(preset) {
      currentRangePreset = preset;
      document.querySelectorAll(".range-btn").forEach(btn => btn.classList.remove("active"));
      event.target.classList.add("active");
      renderChart();
    }

    // Отрисовка профиля калибровки
    function renderProfileDrawer() {
      const ch = rawData.charts[activeChannelId];
      const drawer = document.getElementById("channelProfileDrawer");
      if (!ch) return;

      let cycleText = "Не циклический (линейный мониторинг)";
      let limitText = "Порог медианы + 1σ";
      if (ch.channel_id === "ch_fridge") {
        cycleText = "24 мин ВКЛ / 20 мин ВЫКЛ (медиана)";
        limitText = "53 мин непрерывной работы макс.";
      } else if (ch.channel_id === "ch_base") {
        cycleText = "Постоянный базовый фон 24/7";
        limitText = "0.168 кВт (+40% к фону 0.12 кВт)";
      } else if (ch.channel_id === "ch_coffee") {
        cycleText = "Импульсный режим в рабочие часы";
        limitText = "3.10 кВт (макс. норма 1 фазы)";
      }

      drawer.innerHTML = `
        <div>
          <div class="profile-item-title">Тип оборудования</div>
          <div class="profile-item-value">${ch.channel_type_label}</div>
        </div>
        <div>
          <div class="profile-item-title">Режим работы</div>
          <div class="profile-item-value">${cycleText}</div>
        </div>
        <div>
          <div class="profile-item-title">Порог срабатывания алертов</div>
          <div class="profile-item-value">${limitText}</div>
        </div>
        <div>
          <div class="profile-item-title">Калибровка алгоритма</div>
          <div class="profile-item-value">Медиана ± 1σ (IQR фильтрация шума)</div>
        </div>
      `;
    }

    // Рендер хроники алертов
    function renderAlertsFeed() {
      const grid = document.getElementById("alertsHistoryGrid");
      grid.innerHTML = "";

      const history = [
        {
          time: "01:14",
          channel: "Дежурная сеть 24/7",
          type: "Завышенная ночная база (+287%)",
          desc: "Потребление 0.464 кВт превысило порог 0.168 кВт. Дебаунсинг 15 мин подтвердил забытый включенным прибор.",
          resolved: true
        },
        {
          time: "02:58",
          channel: "Холодильная витрина",
          type: "Нарушение цикличности компрессора",
          desc: "Компрессор непрерывно работал 53 минуты без отключения. Предотвращена порча молочной продукции.",
          resolved: true
        },
        {
          time: "12:09",
          channel: "Кофемашина и гриль",
          type: "Перегрузка в рабочие часы (> 4.3 кВт)",
          desc: "Пиковое потребление 4.475 кВт в течение 31 мин. Своевременное оповещение персонала о риске отключения автомата ввода.",
          resolved: true
        }
      ];

      history.forEach(item => {
        const div = document.createElement("div");
        div.className = `alert-card-item ${item.resolved ? 'resolved' : ''}`;
        div.innerHTML = `
          <div class="alert-card-item-top">
            <span class="alert-card-time">🕒 ${item.time}</span>
            <span style="color: ${item.resolved ? 'var(--success)' : 'var(--danger)'};">
              ${item.resolved ? '✓ Завершен' : '● Активен'}
            </span>
          </div>
          <div style="font-weight: 600; color: #fff; margin-bottom: 2px;">${item.channel} — ${item.type}</div>
          <div style="color: var(--text-muted);">${item.desc}</div>
        `;
        grid.appendChild(div);
      });
    }

    // Отрисовка интерактивного графика (SVG)
    function renderChart() {
      const ch = rawData.charts[activeChannelId];
      if (!ch) return;

      const wrapper = document.getElementById("chartWrapper");
      const svg = document.getElementById("chartSvg");
      const hud = document.getElementById("chartHud");

      const rect = svg.getBoundingClientRect();
      const width = rect.width || 1160;
      const height = rect.height || 360;
      const padding = { top: 24, right: 36, bottom: 42, left: 64 };

      const plotW = width - padding.left - padding.right;
      const plotH = height - padding.top - padding.bottom;

      // Определение среза индексов (Range Preset)
      let startIdx = 0;
      let endIdx = ch.timestamps.length - 1;
      if (currentRangePreset === "night") {
        startIdx = 0;
        endIdx = Math.min(ch.timestamps.length - 1, 6 * 60);
      } else if (currentRangePreset === "day") {
        startIdx = Math.min(ch.timestamps.length - 1, 6 * 60);
        endIdx = Math.min(ch.timestamps.length - 1, 18 * 60);
      } else if (currentRangePreset === "evening") {
        startIdx = Math.min(ch.timestamps.length - 1, 18 * 60);
        endIdx = ch.timestamps.length - 1;
      }

      const totalSlice = endIdx - startIdx + 1;

      // Масштабирование
      const sliceActual = ch.actual_kw.slice(startIdx, endIdx + 1);
      const sliceUpper = ch.corridor_upper.slice(startIdx, endIdx + 1);
      const maxVal = Math.max(...sliceActual, ...sliceUpper) * 1.15 || 1.0;

      const getX = (sliceI) => padding.left + (sliceI / (totalSlice - 1)) * plotW;
      const getY = (val) => padding.top + plotH - (val / maxVal) * plotH;

      // Построение полигона коридора нормы
      let corridorPath = `M ${getX(0)} ${getY(ch.corridor_upper[startIdx])} `;
      for (let i = 1; i < totalSlice; i++) {
        corridorPath += `L ${getX(i)} ${getY(ch.corridor_upper[startIdx + i])} `;
      }
      for (let i = totalSlice - 1; i >= 0; i--) {
        corridorPath += `L ${getX(i)} ${getY(ch.corridor_lower[startIdx + i])} `;
      }
      corridorPath += "Z";

      // Медиана
      let medianPath = `M ${getX(0)} ${getY(ch.median_line[startIdx])} `;
      for (let i = 1; i < totalSlice; i++) {
        medianPath += `L ${getX(i)} ${getY(ch.median_line[startIdx + i])} `;
      }

      // Линия факта
      let factPath = `M ${getX(0)} ${getY(ch.actual_kw[startIdx])} `;
      for (let i = 1; i < totalSlice; i++) {
        factPath += `L ${getX(i)} ${getY(ch.actual_kw[startIdx + i])} `;
      }

      // Площадь под линией факта (мягкий градиент)
      let factArea = `M ${getX(0)} ${getY(ch.actual_kw[startIdx])} `;
      for (let i = 1; i < totalSlice; i++) {
        factArea += `L ${getX(i)} ${getY(ch.actual_kw[startIdx + i])} `;
      }
      factArea += `L ${getX(totalSlice - 1)} ${padding.top + plotH} L ${getX(0)} ${padding.top + plotH} Z`;

      // Сетка и оси Y
      let gridSvg = "";
      const yTicks = 5;
      for (let t = 0; t <= yTicks; t++) {
        const v = (maxVal / yTicks) * t;
        const yPos = getY(v);
        gridSvg += `
          <line x1="${padding.left}" y1="${yPos}" x2="${width - padding.right}" y2="${yPos}" stroke="rgba(255,255,255,0.06)" stroke-dasharray="3,3" />
          <text x="${padding.left - 12}" y="${yPos + 4}" fill="#64748b" font-size="11" font-family="var(--font-mono)" text-anchor="end">${v.toFixed(2)} кВт</text>
        `;
      }

      // Метки времени по оси X
      let xTicksSvg = "";
      const stepSlice = Math.max(1, Math.floor(totalSlice / 8));
      for (let i = 0; i < totalSlice; i += stepSlice) {
        const fullIdx = startIdx + i;
        const xPos = getX(i);
        const timeLabel = ch.timestamps[fullIdx].split(" ")[1] || ch.timestamps[fullIdx];
        xTicksSvg += `
          <line x1="${xPos}" y1="${padding.top + plotH}" x2="${xPos}" y2="${padding.top + plotH + 6}" stroke="rgba(255,255,255,0.15)" />
          <text x="${xPos}" y="${padding.top + plotH + 20}" fill="#94a3b8" font-size="11" font-family="var(--font-mono)" text-anchor="middle">${timeLabel}</text>
        `;
      }

      // Маркеры аномалий
      let markersSvg = "";
      ch.anomaly_markers.forEach(anom => {
        const fullIdx = ch.timestamps.findIndex(t => t === anom.start_time || t.startsWith(anom.start_time));
        if (fullIdx >= startIdx && fullIdx <= endIdx) {
          const sliceI = fullIdx - startIdx;
          const cx = getX(sliceI);
          const cy = getY(anom.power_kw);

          markersSvg += `
            <g class="marker-group" style="cursor: pointer;">
              <circle cx="${cx}" cy="${cy}" r="12" fill="none" stroke="#f43f5e" stroke-width="1.5" class="anomaly-ping" />
              <circle cx="${cx}" cy="${cy}" r="6" fill="#f43f5e" stroke="#ffffff" stroke-width="2" />
            </g>
          `;
        }
      });

      svg.innerHTML = `
        <defs>
          <linearGradient id="factAreaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0"/>
          </linearGradient>
          <filter id="glowLine" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#38bdf8" flood-opacity="0.4"/>
          </filter>
        </defs>

        ${gridSvg}
        ${xTicksSvg}

        <!-- Коридор нормы -->
        <path d="${corridorPath}" fill="var(--corridor-fill)" stroke="var(--corridor-stroke)" stroke-width="1" stroke-dasharray="4,4" />

        <!-- Медиана -->
        <path d="${medianPath}" fill="none" stroke="#64748b" stroke-width="1.2" stroke-dasharray="2,3" />

        <!-- Площадь факта -->
        <path d="${factArea}" fill="url(#factAreaGrad)" />

        <!-- Линия факта с мягким свечением -->
        <path d="${factPath}" fill="none" stroke="#38bdf8" stroke-width="2.2" filter="url(#glowLine)" />

        <!-- Вертикальная линия перекрестья мыши -->
        <line id="crosshairLine" x1="0" y1="${padding.top}" x2="0" y2="${padding.top + plotH}" stroke="rgba(255,255,255,0.4)" stroke-dasharray="3,3" opacity="0" pointer-events="none"/>
        <circle id="crosshairDot" cx="0" cy="0" r="5" fill="#38bdf8" stroke="#ffffff" stroke-width="2" opacity="0" pointer-events="none"/>

        ${markersSvg}
      `;

      // Интерактивное наведение мыши на график (Crosshair HUD)
      const crossLine = document.getElementById("crosshairLine");
      const crossDot = document.getElementById("crosshairDot");

      wrapper.onmousemove = (e) => {
        const svgBox = svg.getBoundingClientRect();
        const mouseX = e.clientX - svgBox.left;
        const mouseY = e.clientY - svgBox.top;

        if (mouseX < padding.left || mouseX > width - padding.right || mouseY < padding.top || mouseY > padding.top + plotH) {
          hud.style.opacity = "0";
          crossLine.style.opacity = "0";
          crossDot.style.opacity = "0";
          return;
        }

        const relativeX = (mouseX - padding.left) / plotW;
        const sliceI = Math.min(totalSlice - 1, Math.max(0, Math.round(relativeX * (totalSlice - 1))));
        const fullIdx = startIdx + sliceI;

        const timeStr = ch.timestamps[fullIdx];
        const valKw = ch.actual_kw[fullIdx];
        const medKw = ch.median_line[fullIdx];
        const upKw = ch.corridor_upper[fullIdx];
        const lowKw = ch.corridor_lower[fullIdx];

        const cx = getX(sliceI);
        const cy = getY(valKw);

        crossLine.setAttribute("x1", cx);
        crossLine.setAttribute("x2", cx);
        crossLine.style.opacity = "1";

        crossDot.setAttribute("cx", cx);
        crossDot.setAttribute("cy", cy);
        crossDot.style.opacity = "1";

        const isExceed = valKw > upKw;
        const deltaPct = Math.round(((valKw - medKw) / (medKw || 0.001)) * 100);

        hud.innerHTML = `
          <div class="hud-time">
            <span>🕒 ${timeStr.split(" ")[1] || timeStr}</span>
            <span style="font-size:11px; color:${isExceed ? 'var(--danger)' : 'var(--success)'}; font-weight:700;">
              ${isExceed ? '🔴 Превышение нормы' : '🟢 В коридоре'}
            </span>
          </div>
          <div class="hud-row">
            <span class="hud-label">Факт мощности:</span>
            <span class="hud-val ${isExceed ? 'alert' : 'actual'}">${valKw.toFixed(3)} кВт</span>
          </div>
          <div class="hud-row">
            <span class="hud-label">Медиана нормы:</span>
            <span class="hud-val">${medKw.toFixed(3)} кВт</span>
          </div>
          <div class="hud-row">
            <span class="hud-label">Коридор (±1σ):</span>
            <span class="hud-val">${lowKw.toFixed(2)} – ${upKw.toFixed(2)} кВт</span>
          </div>
          <div class="hud-row" style="border-top: 1px solid rgba(255,255,255,0.06); padding-top: 4px; margin-top: 4px;">
            <span class="hud-label">Отклонение:</span>
            <span class="hud-val" style="color: ${deltaPct > 0 ? '#fca5a5' : '#94a3b8'};">${deltaPct > 0 ? '+' : ''}${deltaPct}% к норме</span>
          </div>
        `;

        hud.style.opacity = "1";
        hud.style.left = `${cx}px`;
        hud.style.top = `${Math.max(padding.top + 20, cy - 20)}px`;
      };

      wrapper.onmouseleave = () => {
        hud.style.opacity = "0";
        crossLine.style.opacity = "0";
        crossDot.style.opacity = "0";
      };
    }

    window.addEventListener("resize", renderChart);

    // Первоначальная загрузка
    setSnapshot("night_incident");
    renderProfileDrawer();
    renderAlertsFeed();
    setTimeout(renderChart, 60);
  </script>
</body>
</html>
"""
        final_html = html_template.replace("__DATA_JSON__", data_json)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_html)
