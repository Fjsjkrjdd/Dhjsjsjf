#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Peleng / УД2-102/103 ВАГОННАЯ 6.43 — GUI + SQLite.

V9: полный план чтения 10..29, протоколы 4000/6000, русские подписи деталей.
V8: русские подписи, добор отчётов, retry чтения, Плавка.
V6: правки по реальному RAW от прибора:
    • длинная A-развёртка приходит в 4000+n (например 4002), а 6000+n в этом дампе — короткие записи 0x56;
    • graph-block = последний 0xF4-байтный хвост длинной 4000-записи;
    • setting_no для живого raw = LE16(record+0x1C);
    • парсер дат стал авто-подбирающим offset 7/8;
    • чтение настроек по lazy-связи исправлено.

Функции:
  • COM-порт: 0x55 handshake, затем 0x42 + AddrLE16.
  • SQLite: raw_records, reports, protocols, settings.
  • Вкладки: Отчёты контроля / Протоколы А-развёртки / Настройки.
  • Двойной клик по протоколу: полная дешифровка + A-график + ВС1/ВС2.
  • Двойной клик по настройке: внутренняя дешифровка NASTR2.

Версия: ВАГОННАЯ 6.43.
Round31: no-retry transport follows PelengPC.exe: short/timeout is an error/diagnostic, not a repeated request.
Round28: PLG reverse — отчёты читаются структурно <addr><len>, 0x52..0x55 при len=0x56 считаются недочитанным хвостом.
Round29: original transport strict — 42 LL HH идёт как PelengPC.exe: 10 ms между байтами, чтение до expected_len из range-table; отчёты больше не читаются champion body-only reader-ом.
Round32: PelengPC.exe strict original — live 55 как header16+flat WORD ID, PLG/file как block-stream, 42 один раз, receiver до expected_len/short-finalize без повторного запроса.
Round33: receiver idle counter corrected 1:1: original finalizes short frame when empty-event counter already equals 3 (effectively 4 empty reads). Incomplete reports are saved as report_incomplete raw diagnostics, not decoded as valid reports.
Round35: reverse correction: PelengPC 0x411810 is an OnRxChar event handler, not an 8 ms polling loop. Python now waits for the full expected frame in the same 42 request and preserves incomplete frames in raw_events/raw_records without silent overwrite.
Round36: reverse correction: PelengPC 0x423A58 waits by GetTickCount(10), which on the original Windows timer is ~15.6 ms, not exact 10.0 ms. Default inter-byte gap is therefore 16 ms.
Round37: correction: v24 accidentally kept DEFAULT_INTER_BYTE_GAP=0.010; set real 0.016, command cooldown 0.016, and original CPort read timeout 100 ms.
Round38: critical COM reverse fix: PelengPC.exe sets DCB ByteSize=8, Parity=2/EVEN, StopBits=0/1 stop. Original profile is 19200 8E1, not 8N1.

Ключевые offsets для чистого payload 0x42 record:
  protocol→setting: LE16(record+0x1D)
  graph record:     6000+n для протокола 4000+n
  graph bytes:      record[0x1D5 : 0x1D5+0xF4]
  draw points:      первые 0xF3 байта, baseline 0x8C
  ВС1:              threshold 0xC7, method 0xC8, start 0xCD, end 0xCF
  ВС2:              threshold 0xD1, method 0xD2, start 0xD7, end 0xD9

Зависимость:
    python -m pip install pyserial

Запуск:
    python peleng_vagon643_full_gui.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import traceback
import queue
import sqlite3
import sys
import threading
import time
import zipfile
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Optional

# Original zapis2.exe reverse dictionaries.
# Keep the GUI runnable as a single file; if these modules are absent,
# minimal fallbacks below still work, but the bundle includes the full tables.
try:
    from peleng_original_reverse_tables import (
        TYPEVAR_DETAIL as ORIG_TYPEVAR_DETAIL,
        describe_typevar as orig_describe_typevar,
        typevar_detail as orig_typevar_detail,
        typevar_ntd as orig_typevar_ntd,
        typevar_object_hint as orig_typevar_object_hint,
    )
except Exception:  # pragma: no cover
    ORIG_TYPEVAR_DETAIL = {731: "ср.и дал.подступичная часть", 834: "поверхность катания"}
    def orig_typevar_detail(typevar: int) -> str:
        return ORIG_TYPEVAR_DETAIL.get(int(typevar), "")
    def orig_typevar_ntd(typevar: int) -> str:
        return "СТО РЖД 1.11.002-2008 (ТИ 07.73-2009)" if int(typevar) == 731 else ""
    def orig_typevar_object_hint(typevar: int, object_index: int = 0) -> str:
        tv = int(typevar)
        if tv // 100 == 7:
            return "ось РУ1 (РУ1Ш)"
        if tv // 100 == 8:
            return "колесо"
        return ""
    def orig_describe_typevar(typevar: int, object_index: int = 0) -> dict:
        return {"typevar": int(typevar), "object": orig_typevar_object_hint(typevar, object_index), "detail": orig_typevar_detail(typevar), "ntd": orig_typevar_ntd(typevar)}

try:
    from peleng_defect_reverse_tables import DEFECT_CODE_TEXT as ORIG_DEFECT_CODE_TEXT, defect_text as orig_defect_text
except Exception:  # pragma: no cover
    ORIG_DEFECT_CODE_TEXT = {}
    def orig_defect_text(code: int) -> str:
        return ""

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "PelengPC-like ВАГОННАЯ — native basket view"
DB_DEFAULT = "peleng_vagon643.sqlite3"

DEFAULT_BAUD = 19200
DEFAULT_BYTESIZE = 8
DEFAULT_PARITY = "E"
DEFAULT_STOPBITS = 1
# PelengPC.exe CPort reverse: 19200 8E1.  DCB mapping in 0x424020:
#   object+0x10=3 => ByteSize=8; object+0x12=2 => EVENPARITY; object+0x11=0 => ONESTOPBIT.
# 42 sends bytes one-by-one with the 0x423A58 wait between bytes.
DEFAULT_INTER_BYTE_GAP = 0.010  # safe fallback for non-report records; reports use benchmark profile below
# Original "Опросить прибор" sends a single 0x55 and waits until frame tail FF FF.
DEFAULT_HANDSHAKE_COUNT = 1
# These are only safety guards for our synchronous Python reader. The original
# app uses CPort OnRxChar and completes frames by structure, not by a fixed timer.
DEFAULT_FIRST_BYTE_TIMEOUT = 0.120  # Original-style receiver: do not classify slow first byte as empty too early
DEFAULT_BODY_TIMEOUT = 0.350  # Original-style structural read: tolerate gaps inside full frames
# PelengPC.exe OnRxChar receiver finalizes a short response only after repeated
# no-read/event-loop passes, then the caller rejects actual_len != expected_len.
# We model that with 4 empty read events after bytes have started: the original
# checks counter==3 before incrementing it on the no-data path.
ORIGINAL_RX_IDLE_LIMIT = 4  # PelengPC 0x41191D: finalize when empty counter already == 3 => 4th empty read
# PelengPC OnRxChar reads whatever is currently available, up to 0x400 bytes
# (0x411850: ecx=0x400; 0x423F64 read).  It does not request exactly
# "remaining" bytes like a blocking read(size=remaining).  If we publish a
# 0x55/85-byte report and immediately send the next 42, the last checksum byte
# can arrive too late and be discarded by the next input reset.  Round34 keeps
# it in the same request: no retry, only late-tail harvesting before finalizing.
ORIGINAL_RX_CHUNK_MAX = 0x400
ORIGINAL_RX_EVENT_POLL_TIMEOUT = 0.050  # diagnostics only; original OnRxChar is event-driven, not 8 ms idle polling
ORIGINAL_RX_LATE_TAIL_TIMEOUT = 1.500  # same-request wait for missing final checksum byte
ORIGINAL_RX_SHORT_DRAIN_TIMEOUT = 0.250
# Original TCOMPort constructor initializes +0x14 to 1000 ms, but the PelengPC
# open profile at 0x42482A calls 0x423B20 with 0x64: the active read helper
# timeout is 100 ms.  Use this for chunk/event waits; it also matches CPort
# ReadFile-with-ClearCommError behavior better than a 1-second blocking read.
ORIGINAL_RX_BODY_TIMEOUT = 0.100
# C original 0x55 uses FUN_00423F64 direct read until COM helper silence,
# not a structural FF FF stop. Keep a small margin over 100 ms.
ORIGINAL_55_SILENCE_TIMEOUT = 0.650
ORIGINAL_55_MAX_BYTES = 0x80010
DEFAULT_HANDSHAKE_TIMEOUT = 5.0
DEFAULT_REQUEST_TOTAL_TIMEOUT = 2.6
DEFAULT_EXTRA_DRAIN_TIMEOUT = 0.150
# Champion report reader: 2-byte head, FD FF means empty, otherwise read 84-byte tail.
REPORT_HEAD_TIMEOUT = 0.028
REPORT_TAIL_TIMEOUT = 0.150
REPORT_WIRE_MIN_OK = 0x52
REPORT_WIRE_MAX_OK = 0x56
# Тайм-аут без единого байта — это не "пустой адрес" прибора.
# В оригинальном PelengPC повторного 42 на тот же ID нет: short/timeout
# публикуется как actual_len != expected_len и обрабатывается как ошибка связи.
REPORT_TIMEOUT_RETRIES = 0  # Original PelengPC has no per-address retry after a 42 request.
REPORT_TIMEOUT_RETRY_DELAY = 0.000
DEFAULT_TIMING_PROFILE = True
DEFAULT_TIMING_BYTE_MODE = False
# Real timing CSV showed first byte ≈34..41 ms, internal gaps up to ≈21..33 ms,
# and occasional ignored requests.  A small command cooldown reduces lost first attempts.
# UD2102base mass mode: after 42+lo+hi it does 15 * Sleep(10 ms).
DEFAULT_COMMAND_COOLDOWN = 0.000  # safe fallback for non-report records; reports use benchmark profile below

# User UI acceleration profile. Reports are fixed 0x56-byte frames, so after
# the Idx catalogue says that an address exists we do not need the conservative
# 1.5 s late-tail wait used for reverse diagnostics. If a frame is incomplete,
# it is still saved as diagnostic RAW and shown as not ready.
FAST_REPORT_READER = True
# Best stable 218-report benchmark from uploaded 222.zip:
# p0033_g004_cd003_f060_s035_t0450 -> 218/218 exact in ~28.5 s (~7.65 records/s).
BENCHMARK_218_PROFILE_NAME = "p0033_g004_cd003_f060_s035_t0450"
BENCHMARK_218_RECORDS_PER_SEC = 7.65
FAST_REPORT_INTER_BYTE_GAP = 0.004
FAST_REPORT_COMMAND_COOLDOWN = 0.003
FAST_REPORT_FIRST_TIMEOUT = 0.060
FAST_REPORT_TOTAL_TIMEOUT = 0.450
FAST_REPORT_BODY_TIMEOUT = 0.035
FAST_REPORT_POLL_INTERVAL = 0.002
FAST_REPORT_DRAIN_AFTER_EXPECTED = 0.0175
UI_RELOAD_EVERY = 25

REPORT_CONTAINER_EMPTY_LIMIT = 20  # в 55-payload режиме не используется; оставлено для fallback
PROTOCOL_EMPTY_RETRY = 0  # no retry in original PelengPC path
SETTING_EMPTY_RETRY = 0
BAD_PREFIX_RETRY = 0
BAD_PREFIX_DRAIN_TIMEOUT = 0.09
# Native ПО показало, что реальные A-протоколы в BNEW сидят в этих слотах.
# Дубликат 2 из пользовательского списка нормализуем через set при построении плана.
PROTOCOL_NATIVE_SLOTS = (1, 2, 3, 4, 2, 9, 5, 8, 10, 11, 12)
# Champion report scanner that gave 218 records on the real device: scan these
# report buckets with 0..99 offsets and break by empty streaks.
CHAMPION_REPORT_BASES = (10100, 10200, 10300, 10400, 10500, 10600, 13300, 13400)
CHAMPION_PRE_HIT_EMPTY_LIMIT = 15
CHAMPION_POST_HIT_EMPTY_LIMIT = 2
# Round39: подтверждённые группы отчётов контроля реального прибора.
# Это не retry и не синтез "валидных" кадров: по каждому адресу делается один
# original-like 42, а полный отчёт принимается только при actual_len == expected_len.
ORIGINAL_REPORT_SCAN_BASES = CHAMPION_REPORT_BASES
ORIGINAL_REPORT_SCAN_MAX_ROW = 99


# Прямые размеры payload для 0x42 + addr.
LEN_NASTR2 = 0x0176
LEN_ASCAN_4000 = 0x02B6  # PelengPC range table: 4000..4999 -> 0x02B6
# Важно: PelengPC.exe использует таблицу длин по ID, а не rx[2:4].
# Для 6000..6999 оригинал задаёт ожидаемую длину 0x03A6. Первый
# внутренний заголовок таких записей может объявлять 0x56, но это не
# длина всей записи с графиком; останавливаться на 0x56 нельзя.
LEN_ASCAN_6000 = 0x03A6
LEN_BSCAN = 0x0FD6
LEN_SHORTPROT2 = 0x0056
# PLG-файлы оригинальной программы показали, что SHORTPROT2 хранится
# структурно: 16-byte PLG header + 100 слотов по 0x56 байт.
# Поэтому если live-ответ объявил len=0x56, но Python получил 0x52..0x55,
# это не «нормальная короткая запись», а недочитанный хвост.
# Минимум ниже оставлен только для forensic/старых raw, новое чтение требует
# report_wire_complete().
LEN_SHORTPROT2_MIN_WIRE = 0x0053
LEN_SHORTPROT2_MIN_DECODE = 0x002B
# Настройки NASTR2 по reverse = 0x176, но для отладки живого прибора сохраняем
# и показываем частичные ответы. Полная параметрическая расшифровка использует safe_*
# и может заполнить только те поля, которые реально пришли.
LEN_NASTR2_MIN_DECODE = 0x0020

# Финальные offsets A-графика для чистого record 0x42.
SETTING_NO_OFF = 0x0D  # live protocol: номер настройки в record+0x0D
GRAPH_OFF = 0x1B8  # для живого 4000-record: len(record)-0xF4
GRAPH_COPY_LEN = 0xF4
GRAPH_DRAW_COUNT = 0xF3
GRAPH_BASELINE = 0x8C
GRAPH_WIDTH_ORIG = 0x118   # 280 px в zapis2
GRAPH_HEIGHT_ORIG = 0x0C8  # 200 px в zapis2
LINE_FLAG_OFF = 0x128
SPECIAL_GEOMETRY_FLAG_OFF = 0xF0

# Snapshot зон/оверлеев внутри graph-record.
# Live protocol/settings snapshot offsets (validated against original XML for 4002/setting 26).
VS1_THRESHOLD_OFF = 0xB3
VS1_METHOD_OFF = 0xB4
VS1_START_OFF = 0xB5
VS1_END_OFF = 0xB7
VS2_THRESHOLD_OFF = 0xBC
VS2_METHOD_OFF = 0xBD
VS2_START_OFF = 0xBE
VS2_END_OFF = 0xC0
EXTRA_START_OFF = 0xCF   # ВРЧ start in T*10 us
EXTRA_END_OFF = 0xD1     # ВРЧ end in T*10 us

VS1_METHODS = {0: "эхо", 1: "ЗТМ", 2: "теневой", 3: "зеркальный", 4: "2 эхо"}
VS2_METHODS = {0: "эхо", 1: "зтм", 2: "нет"}
SWEEP_TYPES = {0: "100%", 1: "120%", 2: "150%", 3: "200%", 4: "220%", 5: "ручн"}

REPORT_COLS = [
    "NUMBER", "NUMKOD", "DATEFORM", "TIMEFORM", "KODOPERA", "NAMEOPERA",
    "NUMVERS", "NUMPRIB", "TYPEVAR", "NUMOBJ", "SMELTING", "CODEDEF", "PROTOCOL", "NUMZAP",
]

PROTOCOL_COLS = [
    "NUMBER", "NUMKOD", "TYPEZAP", "DATEFORM", "TIMEFORM", "KODOPERA",
    "NAMEOPERA", "NUMVERS", "NUMPRIB", "TYPEVAR", "NUMOBJ", "SMELTING",
    "INDMAKER", "MAKETIME", "DEFEKT", "CODEDEF", "SETTING_NO",
    "SETTING_ADDR", "GRAPH_ADDR", "SPECIAL", "NUMZAP",
]

SETTING_COLS = [
    "NUMBER", "NUMKOD", "TYPEZAP", "DATEFORM", "TIMEFORM", "KODOPERA",
    "NAMEOPERA", "NUMVERS", "NUMPRIB", "SETTING_NO", "TYPEVAR", "NUMZAP",
]

DIAG_COLS = [
    "address", "linked_graph_addr", "setting_addr", "fw_code", "record_len",
    "graph_found", "graph_len", "setting_found", "setting_no",
    "zones_match_setting", "special_geometry", "warnings_json",
]

SUPPORTED_FW_CODES = {0x2A06, 0x2B06}

FIELD_LABELS = {
    "id": "ID", "address": "Адрес", "created_at": "Время чтения", "kind": "Тип", "raw_len": "Длина", "category": "Категория",
    "NUMBER": "№", "NUMKOD": "Код", "TYPEZAP": "Тип записи", "DATEFORM": "Дата", "TIMEFORM": "Время",
    "KODOPERA": "Шифр оператора", "NAMEOPERA": "Оператор", "NUMVERS": "Версия", "NUMPRIB": "№ прибора",
    "TYPEVAR": "Типовой вариант", "NUMOBJ": "№ объекта", "SMELTING": "Плавка",
    "INDMAKER": "Завод", "MAKETIME": "Год", "DEFEKT": "Дефект", "CODEDEF": "Код дефекта / кол-во",
    "PROTOCOL": "Протокол", "NUMZAP": "№ записи", "SETTING_NO": "№ настройки", "SETTING_ADDR": "Адрес настройки",
    "GRAPH_ADDR": "Адрес графика", "SPECIAL": "Спец. режим", "linked_graph_addr": "Связанный график",
    "setting_addr": "Адрес настройки", "fw_code": "FW/type", "record_len": "Длина записи", "graph_found": "График найден",
    "graph_len": "Длина графика", "setting_found": "Настройка найдена", "setting_no": "№ настройки",
    "zones_match_setting": "Зоны совпали", "special_geometry": "Спецгеометрия", "warnings_json": "Предупреждения",
    # Подписи для полной дешифровки протокола/графика.
    "graph.offset": "Смещение графика",
    "graph.copy_len": "Размер блока графика",
    "graph.draw_count": "Точек для отрисовки",
    "graph.baseline": "Базовая линия",
    "graph.min_sample": "Минимум графика",
    "graph.max_sample": "Максимум графика",
    "graph.line_mode": "Режим линии",
    "graph.graph_offset": "Смещение графика",
    "graph.graph_len": "Длина графика",
    "graph.first32": "Первые 32 байта графика",
    "graph.special_geometry": "Спецгеометрия",
    "graph.error": "Ошибка графика",
    "zone.setting_no": "№ настройки",
    "zone.vs1_threshold": "ВС1: порог, %",
    "zone.vs1_method_raw": "ВС1: код метода",
    "zone.vs1_method": "ВС1: метод",
    "zone.vs1_start_raw": "ВС1: начало",
    "zone.vs1_end_raw": "ВС1: конец",
    "zone.vs1_start_px": "ВС1: начало, пикс.",
    "zone.vs1_end_px": "ВС1: конец, пикс.",
    "zone.vs2_threshold": "ВС2: порог, %",
    "zone.vs2_method_raw": "ВС2: код метода",
    "zone.vs2_method": "ВС2: метод",
    "zone.vs2_start_raw": "ВС2: начало",
    "zone.vs2_end_raw": "ВС2: конец",
    "zone.vs2_start_px": "ВС2: начало, пикс.",
    "zone.vs2_end_px": "ВС2: конец, пикс.",
    "zone.extra_start_raw": "Доп./ВРЧ: начало",
    "zone.extra_end_raw": "Доп./ВРЧ: конец",
    "zone.extra_start_px": "Доп./ВРЧ: начало, пикс.",
    "zone.extra_end_px": "Доп./ВРЧ: конец, пикс.",
    "zone.error": "Ошибка зон",
    "diag.fw_code": "Диагностика: FW/type",
    "diag.record_len": "Диагностика: длина записи",
    "diag.linked_graph_addr": "Диагностика: связанный график",
    "diag.graph_found": "Диагностика: график найден",
    "diag.graph_len": "Диагностика: длина графика",
    "diag.setting_addr": "Диагностика: адрес настройки",
    "diag.setting_found": "Диагностика: настройка найдена",
    "diag.zones_match_setting": "Диагностика: зоны совпали с настройкой",
    "diag.special_geometry": "Диагностика: спецгеометрия",
    "diag.warnings_json": "Диагностика: предупреждения",
    # Подписи параметров NASTR2/settings.
    "partial": "Настройка неполная",
    "raw_len": "Фактическая длина",
    "expected_len": "Ожидаемая длина",
    "decode_warning": "Предупреждение дешифровки",
    "operator_code": "Шифр оператора",
    "typevar": "Типовой вариант",
    "freq_mhz_raw": "Частота УЗК, код",
    "sound_speed": "Скорость УЗК, м/с",
    "probe_no": "№ ПЭП",
    "probe_enabled": "ПЭП включён",
    "angle_deg": "Угол ввода, град.",
    "probe_time_raw": "Время в ПЭП, код",
    "thickness_raw": "Толщина, код",
    "gain_raw": "Усиление, код",
    "required_sens_raw": "Треб. чувств., код",
    "actual_sens_raw": "Факт. чувств., код",
    "extra_gain_raw": "Доп. усиление, код",
    "sweep_type_raw": "Тип развёртки, код",
    "sweep_type": "Тип развёртки",
    "sweep_duration_raw": "Длительность развёртки",
    "w_sweep_enabled": "W-развёртка",
    "vs1_threshold_pct": "ВС1: порог, %",
    "vs1_method_raw": "ВС1: код метода",
    "vs1_method": "ВС1: метод",
    "vs1_start_raw": "ВС1: начало",
    "vs1_end_raw": "ВС1: конец",
    "vs2_threshold_pct": "ВС2: порог, %",
    "vs2_method_raw": "ВС2: код метода",
    "vs2_method": "ВС2: метод",
    "vs2_start_raw": "ВС2: начало",
    "vs2_end_raw": "ВС2: конец",
    "aru_start_raw": "АРУ: начало",
    "aru_end_raw": "АРУ: конец",
    "vrch_type_raw": "ВРЧ: тип",
    "vrch_start_raw": "ВРЧ: начало",
    "vrch_end_raw": "ВРЧ: конец",
    "vrch_amp_db_raw": "ВРЧ: амплитуда, код",
    "vrch_shape_raw": "ВРЧ: форма",
    "before_vrch_db_raw": "До ВРЧ, код",
    "after_vrch_db_raw": "После ВРЧ, код",
    "warning": "Предупреждение",
    "error": "Ошибка",
}

FIELD_LABELS.update({
    "object": "Объект",
    "detail": "Деталь",
    "ntd": "НТД на контроль",
    "freq_mhz": "Частота УЗК, МГц",
    "sound_speed": "Скорость УЗК, м/с",
    "probe_no": "№ ПЭП",
    "probe_enabled": "Вкл. ПЭП",
    "angle_deg": "Угол ввода, град.",
    "probe_time_us": "Время в ПЭП, мкс",
    "thickness_mm": "Толщина, мм",
    "gain_db": "Усиление, дБ",
    "required_sens_db": "Треб. чувств., дБ",
    "actual_sens_db": "Факт. чувств., дБ",
    "sweep_duration": "Длительность",
    "w_sweep_enabled": "W-развёртка",
    "envelope_enabled": "Огибающая",
    "vs1_start": "Начало ВС1",
    "vs1_end": "Конец ВС1",
    "vs2_start": "Начало ВС2",
    "vs2_end": "Конец ВС2",
    "aru_enabled": "Вкл. АРУ",
    "aru_start": "Начало АРУ",
    "aru_end": "Конец АРУ",
    "vrch_type": "Тип ВРЧ",
    "vrch_indication": "Индикация ВРЧ",
    "vrch_start": "Начало ВРЧ",
    "vrch_end": "Конец ВРЧ",
    "vrch_amp_db": "Амплитуда ВРЧ, дБ",
    "vrch_shape": "Форма ВРЧ",
    "before_vrch_db": "До ВРЧ, дБ",
    "after_vrch_db": "После ВРЧ, дБ",
    "extra_gain_enabled": "Вкл. доп. усиления",
    "extra_gain_db": "Доп. усиление, дБ",
    "duration_t10": "Длительность, T*10 мкс",
    "defect_y": "Глубина дефекта Y, мм",
    "defect_x": "Расст. до проекции X, мм",
    "defect_r": "Расстояние по лучу R, мм",
    "defect_t": "Время дефекта T, мкс",
    "defect_m": "Кол. отражений луча M",
    "detectability_db": "Коэф. выявляемости, дБ",
})

KIND_LABELS = {
    "setting": "Настройка", "protocol_short": "Протокол А-развёртки", "protocol_graph": "Протокол А-развёртки",
    "bscan": "B-развёртка", "report": "Отчёт контроля", "report_v2": "Отчёт V2", "unknown": "Неизвестно",
}

# Обратный BCD/цифровой формат: 0x0A часто используется как терминатор/заполнитель.
def reverse_digit_field(buf: bytes, off: int, length: int) -> str:
    if off < 0 or off >= len(buf):
        return ""
    data = buf[off:min(len(buf), off + length)]
    digits = []
    for b in data:
        if 0 <= b <= 9:
            digits.append(str(b))
        elif b == 0x0A:
            # Заполнитель/терминатор: не включаем в строку.
            continue
    return "".join(reversed(digits)).lstrip("0") or ("0" if digits else "")

# LUT decoder 0x402708 / PassportLUT.
LUT_VALID = bytes.fromhex(
    "000102030405060708090a0b0c0d0e0f"
    "101112131415161718191a1b1c1d1e1f"
    "202122232425262728292a2b2c2d2e2f"
    "303132333435363738393a3b3c3d3e3f"
    "404142434445464748494a4b4c4d4e4f"
    "505152535455565758595a5b5c5d5e5f"
    "606162636465666768696a6b6c6d6e6f"
    "7071727374757677fcfdfeff"
)
LUT_REPL = bytes.fromhex(
    "303132333435363738392041c142c3c445"
    "c6c7c8c94bcb4d484fcf5043d2d3d7"
    "d4d5d6d8d9dadbdcdddedf2b2d3d51"
    "57652e3f525254545959787972745e3e"
    "3c55494f504153444647484629283a3b"
    "2f2c4a4b5f7b7d5a584343585a4256"
    "6e6473776d674e4e4d4d7625444749"
    "4a4c5155575a26202020205c7c607e"
)


def le16(buf: bytes, off: int) -> int:
    if off < 0 or off + 1 >= len(buf):
        raise ValueError(f"LE16 out of buffer: off=0x{off:X}, len=0x{len(buf):X}")
    return buf[off] | (buf[off + 1] << 8)


def safe_le16(buf: bytes, off: int, default: int = 0) -> int:
    try:
        return le16(buf, off)
    except Exception:
        return default


def safe_u8(buf: bytes, off: int, default: int = 0) -> int:
    return buf[off] if 0 <= off < len(buf) else default


def hexdump_preview(buf: bytes, limit: int = 256) -> str:
    data = buf[:limit]
    lines: list[str] = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02X}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{i:04X}: {hx:<48} {asc}")
    if len(buf) > limit:
        lines.append(f"... ({len(buf)} bytes total)")
    return "\n".join(lines)


def passport_lut(buf: bytes, off: int, length: int) -> str:
    if off < 0 or off + length > len(buf):
        return ""
    out = bytearray()
    started = False
    for i in range(length):
        b = buf[off + length - 1 - i]
        for j, valid in enumerate(LUT_VALID):
            if b == valid:
                if valid == 0 and not started:
                    break
                started = True
                out.append(LUT_REPL[j])
                break
    return out.decode("cp1251", errors="replace").strip()


def _fw_string_from_payload(record: bytes, default: str = "") -> str:
    """Decode firmware version from the same payload bytes as the native build.

    For 0x42 records the normalized payload starts with ``<addr><len>`` and the
    firmware bytes are at offsets 4..5.  Do not scan arbitrary fields: dates,
    counters and object data may contain accidental ``06.xx`` pairs and that was
    the source of wrong versions after the previous change.
    """
    data = bytes(record or b"")
    if len(data) > 5:
        major = int(data[4])
        minor = int(data[5])
        if 1 <= major <= 9 and 0 <= minor <= 99:
            return f"{major}.{minor:02d}"
    return default


def fw_string(record: bytes) -> str:
    """Decode firmware version from payload bytes, with legacy fallback."""
    return _fw_string_from_payload(record, "6.43")


def detect_datetime_offset(record: bytes) -> Optional[int]:
    """Общий поиск DD/MM/YY HH:MM для настроек и A-протоколов."""
    candidates: list[tuple[int, int, int, int, int, int]] = []
    for off in range(6, 16):
        if len(record) <= off + 4:
            continue
        d, m, yy, h, minute = record[off], record[off + 1], record[off + 2], record[off + 3], record[off + 4]
        year = 2000 + yy
        if not (1 <= d <= 31 and 1 <= m <= 12 and 0 <= yy <= 60 and 0 <= h < 24 and 0 <= minute < 60):
            continue
        try:
            dt.date(year, m, d)
        except ValueError:
            continue
        score = abs(year - 2026) * 10 + off
        candidates.append((score, off, d, m, year, h, minute))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def dateform(record: bytes) -> str:
    off = detect_datetime_offset(record)
    if off is None:
        return ""
    d, m, y = record[off], record[off + 1], 2000 + record[off + 2]
    return f"{d:02d}.{m:02d}.{y:04d}"


def timeform(record: bytes) -> str:
    off = detect_datetime_offset(record)
    if off is None:
        return ""
    h, m = record[off + 3], record[off + 4]
    return f"{h:02d}:{m:02d}"



def bcd_to_int(value: int) -> Optional[int]:
    """BCD byte 0x25 -> 25. Возвращает None, если байт не BCD."""
    hi, lo = (value >> 4) & 0x0F, value & 0x0F
    if hi > 9 or lo > 9:
        return None
    return hi * 10 + lo


def byte_or_bcd(value: int) -> Optional[int]:
    """Пытается понять byte как обычное число или BCD."""
    if 0 <= value <= 99:
        # Для 0x25 нужно вернуть 25, а не 37.
        b = bcd_to_int(value)
        if b is not None and value >= 0x10:
            return b
        return value
    return bcd_to_int(value)

def report_date_time(record: bytes) -> tuple[str, str]:
    """Дата/время для live-отчётов контроля.

    В отчётных raw-записях живого прибора найден отдельный формат:
      • день/месяц часто лежат в record[7]/record[8] или record[8]/record[9];
      • год в большинстве нормальных записей лежит в record[2] как BCD/число 25;
      • record[9] часто является минутой, а не годом — именно из-за этого
        старая автоэвристика давала даты вроде 26.11.2042.

    Если год не удаётся определить уверенно, возвращаем дату без года,
    чтобы не показывать ложный 2042/2037.
    """
    if len(record) < 10:
        return "", ""

    # Вариант A: типичный для 10x/102x: DD/MM в 7/8.
    day = record[7] if 1 <= record[7] <= 31 else 0
    month = record[8] if 1 <= record[8] <= 12 else 0

    # Вариант B: часть записей имеет служебный байт перед DD/MM.
    if not (day and month) and 1 <= record[8] <= 31 and 1 <= record[9] <= 12:
        day, month = record[8], record[9]

    if not (day and month):
        # Fallback к общему детектору, но только если год не уходит далеко в будущее.
        off = detect_datetime_offset(record)
        if off is not None:
            y = 2000 + record[off + 2]
            if 2020 <= y <= 2030:
                return f"{record[off]:02d}.{record[off+1]:02d}.{y:04d}", f"{record[off+3]:02d}:{record[off+4]:02d}"
        return "", ""

    year = None
    # report[2] в live RAW часто BCD: 0x25 => 2025.
    y2 = byte_or_bcd(record[2])
    if y2 is not None and 20 <= y2 <= 30:
        year = 2000 + y2
    else:
        # Если год всё же лежит в стандартном DD/MM/YY окне, берём только
        # реалистичный 2020..2030. Не используем record[3] как год: это часто час.
        off = detect_datetime_offset(record)
        if off is not None:
            yy = byte_or_bcd(record[off + 2])
            if yy is not None and 20 <= yy <= 30:
                year = 2000 + yy

    date_s = f"{day:02d}.{month:02d}.{year:04d}" if year else f"{day:02d}.{month:02d}.----"

    # В ряде записей record[9] = минута, record[3] = час; оба могут быть BCD.
    time_s = ""
    hh = byte_or_bcd(record[3])
    mm = byte_or_bcd(record[9])
    if hh is not None and mm is not None and 0 <= hh < 24 and 0 <= mm < 60:
        time_s = f"{hh:02d}:{mm:02d}"
    else:
        hh = byte_or_bcd(record[10])
        mm = byte_or_bcd(record[11])
        if hh is not None and mm is not None and 0 <= hh < 24 and 0 <= mm < 60:
            time_s = f"{hh:02d}:{mm:02d}"

    return date_s, time_s


def report_plausible(record: bytes) -> bool:
    """Отчёты контроля не обязаны начинаться с запрошенного address.
    Поэтому валидируем их по длине и внутренним признакам, а не по LE16(record+0).
    """
    if len(record) < 0x52:
        return False
    d, t = report_date_time(record)
    if d:
        return True
    # Даже если дата не распознана, 0x0A-заполнители в зоне плавки/номера —
    # хороший признак live-отчёта, не случайного ответа.
    filler = record.count(0x0A)
    return filler >= 4


def expected_len_for_addr(addr: int) -> Optional[int]:
    if 1000 <= addr <= 1999:
        return LEN_NASTR2
    if 4000 <= addr <= 4999:
        return LEN_ASCAN_4000
    if 6000 <= addr <= 6999:
        return LEN_ASCAN_6000
    if 5000 <= addr <= 5999:
        return LEN_BSCAN
    if 10000 <= addr <= 19999:
        return LEN_SHORTPROT2
    if 20000 <= addr <= 29999:
        return LEN_SHORTPROT2
    return None


def kind_for_addr(addr: int) -> str:
    if 1000 <= addr <= 1999:
        return "setting"
    if 4000 <= addr <= 4999:
        return "protocol_short"
    if 6000 <= addr <= 6999:
        return "protocol_graph"
    if 5000 <= addr <= 5999:
        return "bscan"
    if 10000 <= addr <= 19999:
        return "report"
    if 20000 <= addr <= 29999:
        return "report_v2"
    return "unknown"


def is_empty_payload(buf: bytes) -> bool:
    """True for real empty markers returned by the device.

    Live BNEW dump showed not only plain FD FF / FF FF, but also
    zero-padded tails like 00 00 ... 00 FD FF.  The previous check treated
    those as non-empty because FD remained after stripping zeros/FF, so such
    garbage could be counted as a short report/protocol.
    """
    if not buf:
        return True
    if len(buf) >= 2 and buf[:2] in (b"\xff\xff", b"\xfd\xff"):
        return True
    if all(b in (0x00, 0xFF) for b in buf):
        return True
    if len(buf) >= 2 and buf[-2:] in (b"\xfd\xff", b"\xff\xff") and all(b == 0x00 for b in buf[:-2]):
        return True
    # Some failed reads are mostly 0xFD padding after a tiny non-structured prefix.
    if len(buf) < 0x20 and buf[-2:] in (b"\xfd\xff", b"\xff\xff") and sum(1 for b in buf if b not in (0x00, 0xFD, 0xFF)) <= 4:
        return True
    return False


def is_wire_empty_marker(buf: bytes) -> bool:
    """True только для явного пустого ответа прибора FD FF / FF FF.

    Важно: b"" означает, что Python не дождался ни одного байта. Это тайм-аут
    обмена/слишком быстрый следующий запрос, а не признак конца контейнера.
    """
    if not buf:
        return False
    if len(buf) >= 2 and buf[:2] in (b"\xff\xff", b"\xfd\xff"):
        return True
    if len(buf) >= 2 and buf[-2:] in (b"\xfd\xff", b"\xff\xff") and all(b == 0x00 for b in buf[:-2]):
        return True
    return False


def report_wire_declared_len(buf: bytes) -> int:
    """Declared SHORTPROT2 length from bytes 2..3, with safe fallback.

    Native .plg files store report buckets as 100 fixed slots where each
    non-empty slot starts with <addr><len>. In the uploaded PLG sample the
    slots are 0x56 bytes. If live reading returns 0x52..0x55 while the
    declared word is 0x56, that is a truncated Python read, not a complete
    report.
    """
    if len(buf) >= 4:
        declared = safe_le16(buf, 2, 0)
        if REPORT_WIRE_MIN_OK <= declared <= REPORT_WIRE_MAX_OK:
            return declared
    return LEN_SHORTPROT2


def report_wire_complete(buf: bytes, addr: int) -> bool:
    """True when report answer is structurally complete for this address."""
    if is_wire_empty_marker(buf):
        return True
    if len(buf) < 4:
        return False
    if safe_le16(buf, 0, -1) != addr:
        return False
    declared = safe_le16(buf, 2, 0)
    if not (REPORT_WIRE_MIN_OK <= declared <= REPORT_WIRE_MAX_OK):
        return False
    return len(buf) >= declared


def report_wire_problem(buf: bytes, addr: int) -> str:
    if not buf:
        return "no-byte timeout"
    if is_wire_empty_marker(buf):
        return "wire-empty"
    if len(buf) < 4:
        return f"short header len=0x{len(buf):X}"
    got = safe_le16(buf, 0, -1)
    declared = safe_le16(buf, 2, 0)
    if got != addr:
        return f"bad prefix 0x{got:04X} != 0x{addr:04X}"
    if not (REPORT_WIRE_MIN_OK <= declared <= REPORT_WIRE_MAX_OK):
        return f"bad declared len=0x{declared:X}"
    if len(buf) < declared:
        missing = declared - len(buf)
        if missing == 1:
            # In PLG samples the last byte of 0x56 SHORTPROT2 makes
            # sum(frame) & 0xFF == 0xFF.  When exactly one byte is absent,
            # this is usually the checksum/tail byte; show the calculated
            # value for reverse diagnostics, but do not synthesize/save it
            # as a valid original record.
            need = (0xFF - (sum(buf) & 0xFF)) & 0xFF
            return f"truncated len=0x{len(buf):X}/0x{declared:X}; missing last/checksum byte would be 0x{need:02X}"
        return f"truncated len=0x{len(buf):X}/0x{declared:X}; missing={missing}"
    return "ok"

def normalize_record_response(resp: bytes, addr: int, expected: int) -> bytes:
    """Возвращает чистый payload record. Учитывает возможную внешнюю 16-byte шапку."""
    if len(resp) >= expected and safe_le16(resp, 0, -1) == addr:
        return resp[:expected]
    if len(resp) >= expected + 0x10 and safe_le16(resp, 0x10, -1) == addr:
        return resp[0x10:0x10 + expected]
    for off in range(0, min(0x40, len(resp) - 1)):
        if safe_le16(resp, off, -1) == addr and off + expected <= len(resp):
            return resp[off:off + expected]
    if len(resp) == expected:
        return resp
    if len(resp) > expected:
        return resp[:expected]
    return resp


def category_of_addr(addr: int) -> int:
    return addr // 1000


def record_addr_matches(record: bytes, addr: int) -> bool:
    """True, если ответ действительно является записью запрошенного адреса.

    Live RAW показал, что иногда из-за таймингов/десинхронизации сохраняется
    короткий хвост или чужой ответ. Такие записи надо хранить в Raw, но нельзя
    дешифровать как отчёт/настройку — иначе появляются даты вроде 2042 года.
    """
    return len(record) >= 2 and safe_le16(record, 0, -1) == addr


def report_protocol_field(record: bytes) -> str:
    # В live-отчётах поле протокола лучше трактовать как цифровое поле с
    # 0x0A/0x00 заполнителями. PassportLUT на этих байтах иногда даёт буквы
    # ("O600000", "Z200000"), поэтому для пользовательской графы оставляем
    # только цифры.
    s = reverse_digit_field(record, 0x21, 0x07)
    if not s:
        s = passport_lut(record, 0x21, 0x07).strip()
        digits = "".join(ch for ch in s if ch.isdigit())
        if digits:
            s = digits
    if s and s.isdigit():
        s = s.rstrip("0") or "0"
    return s


def common_meta(record: bytes, addr: int, device_no: Optional[int], typezap: str, numkod_mod: int) -> dict[str, str]:
    return {
        "NUMBER": "0",
        "NUMKOD": str(addr % numkod_mod),
        "TYPEZAP": typezap,
        "DATEFORM": dateform(record),
        "TIMEFORM": timeform(record),
        "KODOPERA": str(safe_le16(record, 0x15)),
        "NAMEOPERA": " ",
        "NUMVERS": fw_string(record),
        "NUMPRIB": "" if device_no is None else str(device_no),
    }


def is_v643(record: bytes, strict: bool) -> bool:
    if not strict:
        return True
    # Старый reverse видел версию в record[4:6]. Живой raw из прибора для 4000/10000
    # начинается как <addr><len>, поэтому record[4:6] может быть не версией.
    # В строгом режиме принимаем либо старый признак, либо валидный peleng-сегмент с addr/len.
    if len(record) > 5 and record[4] == 6 and record[5] == 43:
        return True
    if len(record) >= 4:
        seg_id = safe_le16(record, 0)
        seg_len = safe_le16(record, 2)
        if 1000 <= seg_id <= 29999 and 0x40 <= seg_len <= 0x1000:
            return True
    return False




def bcd_or_dec_live(value: int) -> int:
    b = bcd_to_int(value)
    if b is not None and value >= 0x10:
        return b
    return value


def report_body_and_layout(record: bytes, addr: int) -> tuple[bytes, str]:
    """Live reports have two wire variants.

    Variant A: body-only, length 0x52..0x56.
    Variant B: addr+len prefix followed by a truncated body fragment.  In B the
    first 3 bytes of the body are absent, so date/year must be reconstructed
    conservatively.
    """
    if len(record) >= 4 and safe_le16(record, 0, -1) == addr and 0x50 <= safe_le16(record, 2, 0) <= 0x56:
        return record, "addr_len_truncated"
    return record, "body_only"



def live_report_date_time(record: bytes, addr: int, year_hint: int | None = None) -> tuple[str, str]:
    body, layout = report_body_and_layout(record, addr)
    try:
        if layout == "addr_len_truncated":
            # Example: [addr][len][..][HH][..][DD][MM][MIN]. Year may be absent.
            day = safe_u8(body, 0x08)
            month = safe_u8(body, 0x09)
            minute = safe_u8(body, 0x0A)
            hour = safe_u8(body, 0x04)
            year = year_hint or 2025
        else:
            day = safe_u8(body, 0x07)
            month = safe_u8(body, 0x08)
            minute = safe_u8(body, 0x09)
            hour = safe_u8(body, 0x03)
            year = 2000 + safe_u8(body, 0x02)
        if _valid_date_time(day, month, year, hour, minute):
            return f"{day:02d}.{month:02d}.{year:04d}", f"{hour:02d}:{minute:02d}"

        # Fallback: generic DD MM YY HH MM scan, decimal bytes first.
        d, t = best_datetime(record, (0x07, 0x08, 0x04, 0x06))
        return d, t
    except Exception:
        return "", ""


def _round_half_up_float(value: float, digits: int = 1) -> float:
    q = Decimal("1") if digits <= 0 else Decimal("1." + "0" * digits)
    return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))


def _fmt1(value: float) -> str:
    return f"{_round_half_up_float(value, 1):.1f}"


def coord13(raw_t10: int, speed_m_s: int = 5900, angle_deg: float = 0.0) -> dict[str, float]:
    """Original type 0x13 coordinate.

    Recovered from zapis2.exe and verified by настройка_26.xml + setting_1026.bin:
      T_us = raw / 10
      R_mm = T_us * speed / 2000
      Y/X use angle * 6.28 / 360, matching original code.
    """
    import math
    t_us = raw_t10 / 10.0
    r_mm = t_us * speed_m_s / 2000.0
    a = angle_deg * 6.28 / 360.0
    y_mm = r_mm * math.cos(a)
    x_mm = r_mm * math.sin(a)
    return {"Y": y_mm, "R": r_mm, "T": t_us, "X": x_mm}


def format_coord13(raw_t10: int, speed_m_s: int = 5900, angle_deg: float = 0.0) -> str:
    c = coord13(raw_t10, speed_m_s, angle_deg)
    return f"Y{_fmt1(c['Y'])}мм,R{_fmt1(c['R'])}мм,Т{_fmt1(c['T'])}мкс"


def sweep12_to_time_us(raw: int, scale_shift: int = 0, beam_factor: float = 1.0) -> float:
    """Original type 0x12 duration/delay.

    Verified by setting_1026.bin/XML #26: raw @0x58 = 33, scale_shift=0,
    33 * (0xF0 >> 0) / 10 = 792.0 мкс.
    The old 270*44/15 was a false match: 270 is SO-zone end, not duration.
    """
    scale_shift = max(0, min(7, int(scale_shift)))
    return raw * (0xF0 >> scale_shift) / (beam_factor * 10.0)


def format_sweep12(raw: int, speed_m_s: int = 5900, angle_deg: float = 0.0, scale_shift: int = 0) -> str:
    import math
    t_us = sweep12_to_time_us(raw, scale_shift=scale_shift)
    r_mm = t_us * speed_m_s / 2000.0
    y_mm = r_mm * math.cos(angle_deg * 6.28 / 360.0)
    return f"Y{_fmt1(y_mm)}мм,R{_fmt1(r_mm)}мм,Т{_fmt1(t_us)}мкс"


def db_from_negative_byte(b: int) -> int:
    return -int(b)


# ---------------------------------------------------------------------------
# Reverse 1:1 core, corrected from original zapis2.exe
# ---------------------------------------------------------------------------
# There are two related values in live data:
#   1) catalog TYPEVAR: 3-digit codes such as 731/834, decoded by original
#      functions at zapis2.exe 0x411FA0/0x412D47;
#   2) object-word TYPEVAR in some SHORTPROT2 rows: 24667..24672, which are
#      Delphi/Pascal words identifying object text list entries. They are not
#      catalog detail codes, but the original UI still shows them in TYPEVAR-like
#      columns, so we must decode them instead of scanning past them.
ORIG_OBJECT_WORD_TYPEVAR = {
    24667: "ось РУ1",
    24668: "ось РУ1Ш",
    24669: "внут.к-цо подш",
    24670: "нар.к-цо подш",
    24671: "упор.к-цо подш",
    24672: "колесо",
}
KNOWN_TYPEVAR_CODES = dict(ORIG_TYPEVAR_DETAIL)
KNOWN_TYPEVAR_CODES.update(ORIG_OBJECT_WORD_TYPEVAR)

# Confirmed setting link from original/XML branch: setting/protocol №26 -> TYPEVAR 731.
SETTING_TYPEVAR_FALLBACK_BY_NO = {26: 731}

# Наборы offsets. Для live RAW были две ветки: prefix/live и сдвинутый fragment.
SETTING_LAYOUTS = {
    "live_prefixed": {
        "freq_off": 0x04, "freq_div": 8.0,
        "date_off": 0x06,
        "probe_time_off": 0x10,   # u16/10; verified by setting_1026.bin/XML #26
        "probe_time_div": 10.0,
        "probe_no_off": 0x1A,
        "speed_off": 0x26,        # u16; verified 0x170C = 5900
        "angle_off": 0x28,
        "extra_gain_off": 0xE7,
        "required_sens_off": 0x43,
        "actual_sens_off": 0x44,
        "gain_off": 0x45,
        "sweep_type_off": 0x5C,
        "duration_off": 0x58,     # type 0x12 raw; 33 -> 792.0 мкс, 0x56 is SO end
        "delay_off": 0x5A,
        "vs1_thr_off": 0x63, "vs1_method_off": 0x64, "vs1_start_off": 0x65, "vs1_end_off": 0x67,
        "vs2_thr_off": 0x6C, "vs2_method_off": 0x6D, "vs2_start_off": 0x6E, "vs2_end_off": 0x70,
        "vrch_type_off": 0x7B, "vrch_start_off": 0x7F, "vrch_end_off": 0x81,
        "vrch_shape_off": 0x87, "vrch_amp_off": 0x88, "before_vrch_off": 0x89, "after_vrch_off": 0x8A,
    },
    "live_shifted": {
        # Variant where the beginning is shifted/truncated by one byte: BNEW has
        # examples with freq=0x14 at 0x03 and date at 0x05.
        "freq_off": 0x03, "freq_div": 8.0,
        "date_off": 0x05,
        "probe_time_off": 0x07,
        "probe_time_div": 10.0,
        "probe_no_off": 0x19,
        "speed_off": 0x26,
        "angle_off": 0x28,
        "extra_gain_off": 0x41,
        "required_sens_off": 0x42,
        "actual_sens_off": 0x43,
        "gain_off": 0x44,
        "sweep_type_off": 0x5B,
        "duration_off": 0x55,
        "vs1_thr_off": 0x62, "vs1_method_off": 0x63, "vs1_start_off": 0x64, "vs1_end_off": 0x66,
        "vs2_thr_off": 0x6B, "vs2_method_off": 0x6C, "vs2_start_off": 0x6D, "vs2_end_off": 0x6F,
        "vrch_type_off": 0x75, "vrch_start_off": 0x7E, "vrch_end_off": 0x80,
        "vrch_shape_off": 0x86, "vrch_amp_off": 0x87, "before_vrch_off": 0x88, "after_vrch_off": 0x89,
    },
    "legacy_v14": {
        # Старые offsets оставлены как fallback для уже сохранённых/старых дампов.
        "freq_off": 0x04, "freq_div": 8.0,
        "date_off": 0x06,
        "probe_time_off": 0x08,
        "probe_time_div": 10.0,
        "probe_no_off": 0x1A,
        "speed_off": 0x26,
        "angle_off": 0x28,
        "extra_gain_off": 0xE7,
        "required_sens_off": 0x43,
        "actual_sens_off": 0x44,
        "gain_off": 0x45,
        "sweep_type_off": 0x5B,
        "duration_off": 0x55,
        "vs1_thr_off": 0x62, "vs1_method_off": 0x63, "vs1_start_off": 0x64, "vs1_end_off": 0x66,
        "vs2_thr_off": 0x6B, "vs2_method_off": 0x6C, "vs2_start_off": 0x6D, "vs2_end_off": 0x6F,
        "vrch_type_off": 0x76, "vrch_start_off": 0x7E, "vrch_end_off": 0x80,
        "vrch_shape_off": 0x86, "vrch_amp_off": 0x87, "before_vrch_off": 0x88, "after_vrch_off": 0x89,
    },
}


def _valid_date_time(day: int, month: int, year: int, hour: int, minute: int) -> bool:
    if not (1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2035 and 0 <= hour < 24 and 0 <= minute < 60):
        return False
    try:
        dt.date(year, month, day)
        return True
    except ValueError:
        return False


def _decode_datetime_at(buf: bytes, off: int, bcd_year: bool = False) -> tuple[str, str, int]:
    """Return (date, time, score) for DD MM YY HH MM at off, or blanks.

    Live Peleng RAW uses decimal bytes for dates: 0x19 is decimal 25, not BCD 19.
    Therefore we try raw decimal first and only use BCD fallback if decimal is invalid.
    """
    if off < 0 or off + 4 >= len(buf):
        return "", "", -10_000

    def as_dec(v: int) -> int:
        return v if 0 <= v <= 99 else (bcd_to_int(v) or v)

    variants = []
    raw_vals = (safe_u8(buf, off), safe_u8(buf, off + 1), safe_u8(buf, off + 2), safe_u8(buf, off + 3), safe_u8(buf, off + 4))
    variants.append(raw_vals)
    variants.append(tuple(as_dec(v) for v in raw_vals))
    for day, month, yy_raw, hour, minute in variants:
        yy = bcd_or_dec_live(yy_raw) if bcd_year else yy_raw
        year = 2000 + yy
        if _valid_date_time(day, month, year, hour, minute):
            score = 1000 - abs(year - 2025) * 10 - off
            return f"{day:02d}.{month:02d}.{year:04d}", f"{hour:02d}:{minute:02d}", score
    return "", "", -10_000


def best_datetime(buf: bytes, preferred_offsets: tuple[int, ...] = (), bcd_year: bool = False) -> tuple[str, str]:
    candidates: list[tuple[int, str, str]] = []
    for off in preferred_offsets + tuple(range(0, min(len(buf) - 4, 24))):
        d, t, score = _decode_datetime_at(buf, off, bcd_year=bcd_year)
        if d:
            candidates.append((score, d, t))
    if not candidates:
        return "", ""
    candidates.sort(reverse=True)
    return candidates[0][1], candidates[0][2]


def _digit_score(s: str, max_len: int) -> int:
    if not s:
        return -1000
    if not s.isdigit():
        return -500
    if set(s) <= {"0"}:
        return -200
    if len(s) > max_len + 2:
        return -100
    return len(s) * 10 - (5 if s.startswith("0") else 0)


def best_reverse_digit_field(buf: bytes, candidates: tuple[tuple[int, int], ...], max_len: int = 12) -> str:
    """Choose best reverse digit field among candidate offsets.

    Паспортные цифровые поля в приборе часто записаны в обратном порядке с
    заполнителями 0x0A. Эта функция нужна для NUMOBJ/SMELTING/PROTOCOL, чтобы
    один ошибочный offset не давал мусор вместо номера объекта или плавки.
    """
    scored: list[tuple[int, str]] = []
    for off, ln in candidates:
        s = reverse_digit_field(buf, off, ln)
        scored.append((_digit_score(s, max_len), s))
        lut = passport_lut(buf, off, ln)
        digits = "".join(ch for ch in lut if ch.isdigit())
        if digits:
            scored.append((_digit_score(digits, max_len) - 2, digits))
    scored.sort(reverse=True)
    return scored[0][1] if scored and scored[0][0] > -100 else ""


def clean_code_text(s: str) -> str:
    s = (s or "").strip()
    return "" if set(s) <= {"0", " "} else s


def report_defect_count_643(body: bytes) -> str:
    """SHORTPROT2.CODEDEF / "К-во деф" from original zapis2 table.

    Round 13 reverse fixed the field: grid row "К-во деф" is descriptor
    working 0x2C and the real live/raw byte for our captured SHORTPROT2 rows
    is 0x0C.  Older code read 0x2A/0x2E and therefore often displayed 0 or
    random bytes from TYPEVAR/protocol area.
    """
    v = safe_u8(body, 0x0C, 255)
    return str(v) if 0 <= v <= 99 else ""


def shortprot_datetime_643(body: bytes) -> tuple[str, str]:
    """Date/time formatter compatible with original type 0x06.

    In zapis2.exe the SHORTPROT2 table labels DATE at working 0x27, but the
    renderer uses the prepared grid-row buffer, and in live raw the valid
    five-byte DD MM YY HH MM window starts at 0x06.  Offset 0x07 is a trap:
    it produces dates like 26.09.2025 from bytes that are actually
    01 02 26 09 27 => 01.02.2026 09:27.
    """
    d, t = best_datetime(body, (0x06, 0x07, 0x04, 0x08))
    return d, t


def typevar_info_643(typevar: int) -> dict[str, str]:
    tv = int(typevar or 0)
    if tv in ORIG_OBJECT_WORD_TYPEVAR:
        return {"object": ORIG_OBJECT_WORD_TYPEVAR[tv], "detail": "", "ntd": ""}
    d = orig_describe_typevar(tv) if tv else {"object": "", "detail": "", "ntd": ""}
    return {"object": str(d.get("object", "")), "detail": str(d.get("detail", "")), "ntd": str(d.get("ntd", ""))}


def typevar_display(code: int) -> str:
    if not code:
        return ""
    tv = int(code)
    if tv in ORIG_OBJECT_WORD_TYPEVAR:
        return f"{tv} — {ORIG_OBJECT_WORD_TYPEVAR[tv]}"
    info = typevar_info_643(tv)
    detail = info.get("detail", "")
    obj = info.get("object", "")
    if obj and detail:
        return f"{tv} — {obj} / {detail}"
    if detail:
        return f"{tv} — {detail}"
    return str(tv)


def _plausible_typevar(v: int) -> bool:
    # Original catalog codes are 3-digit/low 900 range in recovered tables.
    # Reject false LE16 words from CP1251 strings and record lengths.
    if v in KNOWN_TYPEVAR_CODES:
        return True
    return False


def detect_typevar_code(record: bytes, preferred_offsets: tuple[int, ...] = (), setting_no: int = 0) -> int:
    # Confirmed by original XML/RAW: setting/protocol №26 has TYPEVAR 731.
    # In protocol records nearby small LE16 values can look plausible (e.g. 2570),
    # but they are not TYPEVAR. Use confirmed setting fallback before unknown small candidates.
    if setting_no in SETTING_TYPEVAR_FALLBACK_BY_NO:
        return SETTING_TYPEVAR_FALLBACK_BY_NO[setting_no]

    # 1) offsets supplied by caller: exact layout candidates.
    for off in preferred_offsets:
        v = safe_le16(record, off, 0)
        if _plausible_typevar(v):
            return v

    # 2) known report/protocol/settings offsets seen across branches.
    for off in (0x29, 0x2D, 0x28, 0x2C, 0x3A, 0x3C, 0x40, 0x42):
        v = safe_le16(record, off, 0)
        if v in KNOWN_TYPEVAR_CODES:
            return v

    # 3) scan beginning for known Delphi/Pascal detail codes.
    max_off = max(0, min(len(record) - 1, 0x80))
    scan_start = 4 if len(record) >= 4 else 0
    for off in range(scan_start, max_off):
        v = safe_le16(record, off, 0)
        if v in KNOWN_TYPEVAR_CODES:
            return v

    # 4) only then fall back to small catalog numbers near plausible zones.
    # Do not scan arbitrary small numbers in the prefix/header area: addresses
    # like 1026/4002 otherwise look like valid catalog numbers. Only use
    # caller-provided offsets for unknown small TYPEVAR values.
    for off in preferred_offsets:
        v = safe_le16(record, off, 0)
        if _plausible_typevar(v):
            return v

    # 5) confirmed XML fallback for setting/protocol №26 only.
    return SETTING_TYPEVAR_FALLBACK_BY_NO.get(setting_no, 0)


def setting_layout_score(record: bytes, layout: dict[str, int | float]) -> int:
    score = 0
    freq_raw = safe_u8(record, int(layout["freq_off"]))
    freq = freq_raw / float(layout["freq_div"])
    if 0.5 <= freq <= 15.0:
        score += 10
    if abs(freq - 2.5) < 0.01:
        score += 4
    speed = safe_le16(record, int(layout["speed_off"]), 0)
    if 1000 <= speed <= 10000:
        score += 10
    if speed == 5900:
        score += 4
    duration = safe_le16(record, int(layout["duration_off"]), 0)
    if 10 <= duration <= 2000:
        score += 8
    for key in ("vs1_thr_off", "vs2_thr_off"):
        thr = safe_u8(record, int(layout[key]), 255)
        if 0 <= thr <= 100:
            score += 4
    if safe_u8(record, int(layout["vs1_method_off"]), 255) in VS1_METHODS:
        score += 4
    if safe_u8(record, int(layout["vs2_method_off"]), 255) in VS2_METHODS:
        score += 4
    d, _ = best_datetime(record, (int(layout.get("date_off", 0)),))
    if d:
        score += 6
    return score


def select_setting_layout(record: bytes) -> tuple[str, dict[str, int | float]]:
    scored = sorted(((setting_layout_score(record, cfg), name, cfg) for name, cfg in SETTING_LAYOUTS.items()), reverse=True)
    return scored[0][1], scored[0][2]


def setting_record_acceptable(record: bytes, addr: int) -> bool:
    """True when a setting can be decoded for this requested address.

    Preferred case is a synchronized record with LE16(record+0)==addr.  Some
    historical RAW dumps contain shifted/truncated settings where the address
    prefix is missing, but the NASTR2 body is still intact.  We accept those
    only when the body layout is plausible and the first LE16 is not clearly
    a different setting address.
    """
    if record_addr_matches(record, addr):
        return True
    if len(record) < 0x140:
        return False
    got = safe_le16(record, 0, -1)
    if 1000 <= got <= 1999 and got != addr:
        return False
    try:
        score = max(setting_layout_score(record, cfg) for cfg in SETTING_LAYOUTS.values())
    except Exception:
        score = 0
    if score < 30:
        return False
    shifted_markers = (
        record[:3] == b"\x0d\x76\x01",
        len(record) >= 3 and safe_le16(record, 1, 0) == LEN_NASTR2,
        len(record) >= 4 and record[2:4] in (b"\x0b\x14", b"\x0b\x94"),
    )
    return any(shifted_markers)


def decode_defect_643(record: bytes, speed_m_s: int = 5900, angle_deg: float = 0.0) -> dict[str, Any]:
    """Decode only the confirmed RESULTS2 defect fields.

    Previous builds treated raw[0x60] as a defect coordinate.  Round 15 showed
    that in RESULTS2 v6.43 this area belongs to object/aux fields:
      raw[0x5E] = object word (e.g. 24667), raw[0x60..] = side/neck/rim area.
    Therefore raw[0x60] must not make DEFEKT='есть'.  Until the exact
    PelengPC/zapis2 defect flag offset is finished, we expose CODEDEF only when
    the 5-digit field at 0x21 looks real and maps to the original defect table.
    """
    numeric_code = best_reverse_digit_field(record, ((0x21, 0x07), (0x22, 0x07)), 8)
    code_text = clean_code_text(passport_lut(record, 0x21, 0x07))

    mapped_defect = ""
    if numeric_code.isdigit():
        mapped_defect = orig_defect_text(int(numeric_code))
    if mapped_defect:
        code_text = f"{numeric_code} — {mapped_defect}"

    # Do not use coordinates or object words as a defect-present flag.
    present = bool(mapped_defect or (numeric_code.isdigit() and int(numeric_code) > 0))

    return {
        "defect_present": present,
        "defect_code_text": code_text if present else "",
        "defect_code_numeric": numeric_code if present else "",
        "defect_raw_t10": 0,
        "defect_y": 0.0,
        "defect_x": 0.0,
        "defect_r": 0.0,
        "defect_t": 0.0,
        "defect_m": "",
        "detectability_db": "",
    }


def decode_report_643(record: bytes, addr: int, device_no: Optional[int], strict: bool) -> dict[str, str]:
    if len(record) < LEN_SHORTPROT2_MIN_DECODE:
        raise ValueError(f"SHORTPROT2 too short for decoded fields: 0x{len(record):X}, need at least 0x{LEN_SHORTPROT2_MIN_DECODE:X}")
    if addr // 1000 not in range(10, 30):
        raise ValueError(f"not report addr: {addr}")
    if not is_v643(record, strict):
        raise ValueError(f"not 6.43: {fw_string(record)}")

    body, layout = report_body_and_layout(record, addr)
    out = common_meta(body, addr, device_no, "", 10000)

    # Date/time and operator: use the original SHORTPROT2 table path.
    # raw[0x06..0x0A] is DD MM YY HH MM; raw[0x05] is operator code.
    # raw[0x0C] is not operator, it is "К-во деф".
    rep_date, rep_time = shortprot_datetime_643(body)
    out["DATEFORM"] = rep_date
    out["TIMEFORM"] = rep_time
    out["KODOPERA"] = f"{safe_u8(body, 0x05):02d}" if len(body) > 0x05 else ""

    if layout == "body_only":
        numobj = best_reverse_digit_field(body, ((0x10, 0x0B), (0x11, 0x0B), (0x12, 0x0B), (0x14, 0x0B)), 12)
        smelting = best_reverse_digit_field(body, ((0x33, 0x07), (0x34, 0x07), (0x35, 0x07), (0x36, 0x07)), 8)
        typevar = detect_typevar_code(body, (0x29, 0x28, 0x2A))
        codedef = report_defect_count_643(body)
        proto = report_protocol_field(body) or best_reverse_digit_field(body, ((0x21, 0x07), (0x22, 0x07)), 8)
    else:
        # Prefix/truncated: the first body bytes may be shifted. Use candidate scan.
        numobj = best_reverse_digit_field(body, ((0x13, 0x0B), (0x14, 0x0B), (0x10, 0x0B), (0x11, 0x0B)), 12)
        smelting = best_reverse_digit_field(body, ((0x33, 0x07), (0x34, 0x07), (0x35, 0x07), (0x36, 0x07)), 8)
        typevar = detect_typevar_code(body, (0x2D, 0x2C, 0x29, 0x28))
        codedef = report_defect_count_643(body)
        proto = report_protocol_field(body) or best_reverse_digit_field(body, ((0x21, 0x07), (0x25, 0x07)), 8)

    out.update({
        "TYPEVAR": typevar_display(typevar),
        "NUMOBJ": numobj,
        "SMELTING": smelting,
        "CODEDEF": codedef,
        "PROTOCOL": proto,
        "NUMZAP": "",
    })
    return {c: out.get(c, "") for c in REPORT_COLS}

def protocol_setting_no_643(record: bytes) -> int:
    """Return setting number used by an A-scan protocol.

    Long 4000+n records store it at 0x0D. Short 6000+n summary records in
    BNEW store the first small LE16 at 0x0C; using 0x0D produced bogus values
    like 512/2816 and made lazy setting lookup useless.
    """
    raw_addr = safe_le16(record, 0, -1) if len(record) >= 2 else -1
    if 6000 <= raw_addr <= 6999 and len(record) < 0x60:
        for off in (0x0C, 0x0E, 0x10, SETTING_NO_OFF):
            v = safe_le16(record, off, 0)
            if 0 < v <= 999:
                return v
        return 0

    for off in (SETTING_NO_OFF, 0x0C, 0x1C, 0x1D):
        v = safe_le16(record, off, 0)
        if 0 < v <= 999:
            return v
    return 0


def protocol_setting_addr_643(record: bytes) -> int:
    return 1000 + protocol_setting_no_643(record)


def graph_addr_for_protocol(addr: int) -> int:
    # Оригинальный zapis2.exe отправляет 6000..6999 в тот же RESULTS2/A-scan
    # класс, что и длинные 4000-record.  Поэтому график должен строиться из
    # самой считанной записи, а не из искусственного 4000+n fallback.
    if 4000 <= addr <= 4999:
        return addr
    if 6000 <= addr <= 6999:
        return addr
    raise ValueError(f"not A-scan addr: {addr}")


def decode_protocol_ascan_643(record: bytes, addr: int, device_no: Optional[int], strict: bool) -> dict[str, str]:
    if not (4000 <= addr <= 4999 or 6000 <= addr <= 6999):
        raise ValueError(f"not A-scan addr: {addr}")
    if len(record) < 0x40:
        raise ValueError(f"A-scan too short: 0x{len(record):X}")
    if not is_v643(record, strict):
        raise ValueError(f"not 6.43: {fw_string(record)}")

    setting_no = protocol_setting_no_643(record) if len(record) > SETTING_NO_OFF + 1 else 0
    graph_addr = graph_addr_for_protocol(addr)
    special = "да" if len(record) > SPECIAL_GEOMETRY_FLAG_OFF and record[SPECIAL_GEOMETRY_FLAG_OFF] == 3 else "нет"
    out = common_meta(record, addr, device_no, "Протокол А-развёртки", 1000)

    pdate, ptime = best_datetime(record, (0x06, 0x07, 0x04, 0x08))
    if not pdate:
        pdate, ptime = live_report_date_time(record, addr)
    out["DATEFORM"] = pdate
    out["TIMEFORM"] = ptime
    # RESULTS2 table: operator code is working 0x25 -> raw 0x05.
    # raw 0x0C can be a setting/aux byte in 600x and caused bogus operator codes.
    out["KODOPERA"] = f"{safe_u8(record, 0x05):02d}" if len(record) > 0x05 else ""

    # Если старый RAW уже обрезан до 0x45..0x56, показываем его как неполный,
    # но НЕ делаем вывод, что такой протокол мусорный. При новом чтении 600x
    # должен приходить полным RESULTS2 и пойдёт по обычной A-scan ветке ниже.
    if len(record) < 0x60:
        # The old saved 600x RAWs are truncated before the original RESULTS2
        # graph/data area.  Do not scan TYPEVAR/NUMOBJ/CODEDEF from the fragment:
        # it produces convincing but false values such as TYPEVAR 512 and NUMOBJ
        # 1111110111.  Keep only the link fields that are safe.
        out.update({
            "TYPEZAP": "Протокол А-развёртки (неполный RAW; перечитать)",
            "TYPEVAR": "",
            "NUMOBJ": "",
            "SMELTING": "",
            "INDMAKER": "",
            "MAKETIME": "",
            "DEFEKT": "",
            "CODEDEF": "",
            "SETTING_NO": "" if setting_no == 0 else str(setting_no),
            "SETTING_ADDR": "" if setting_no == 0 else str(1000 + setting_no),
            "GRAPH_ADDR": str(graph_addr),
            "SPECIAL": special,
            "NUMZAP": "",
        })
        return {c: out.get(c, "") for c in PROTOCOL_COLS}

    speed = safe_le16(record, 0x77, 5900)
    if not (1000 <= speed <= 10000):
        speed = 5900
    angle = 0.0
    defect = decode_defect_643(record, speed, angle)
    typevar = detect_typevar_code(record, (0x29, 0x2D, 0x3A, 0x3C), setting_no=setting_no)

    out.update({
        "TYPEVAR": typevar_display(typevar),
        "NUMOBJ": best_reverse_digit_field(record, ((0x10, 0x0B), (0x11, 0x0B), (0x12, 0x0B), (0x14, 0x0B)), 12),
        "SMELTING": best_reverse_digit_field(record, ((0x33, 0x07), (0x34, 0x07), (0x35, 0x07), (0x36, 0x07)), 8) or "0",
        "INDMAKER": str(safe_le16(record, 0x3C)) if safe_le16(record, 0x3C) else "",
        "MAKETIME": str(safe_le16(record, 0x3E)) if safe_le16(record, 0x3E) else "",
        "DEFEKT": "есть" if defect["defect_present"] else "нет",
        "CODEDEF": defect["defect_code_text"] or defect["defect_code_numeric"],
        "SETTING_NO": "" if setting_no == 0 else str(setting_no),
        "SETTING_ADDR": "" if setting_no == 0 else str(1000 + setting_no),
        "GRAPH_ADDR": str(graph_addr),
        "SPECIAL": special,
        "NUMZAP": "",
    })
    return {c: out.get(c, "") for c in PROTOCOL_COLS}

def real48_to_float(data: bytes, off: int) -> float:
    b = data[off:off + 6]
    if len(b) < 6:
        raise ValueError("not enough bytes for Real48")
    exponent = b[0]
    if exponent == 0:
        return 0.0
    sign = -1.0 if (b[5] & 0x80) else 1.0
    mantissa = ((b[5] & 0x7F) << 32) | (b[4] << 24) | (b[3] << 16) | (b[2] << 8) | b[1]
    return sign * (1.0 + mantissa / (1 << 39)) * (2.0 ** (exponent - 129))



def decode_nastr2_params_643(record: bytes, addr: Optional[int] = None) -> dict[str, Any]:
    """Live NASTR2 decoder with layout autodetection.

    Verified formulas from XML #26:
      type 0x13: raw = T*10 us; R = T_us*speed/2000; Y/X by angle.
      type 0x12: T_us = raw*(0xF0>>scale_shift)/10; setting #26 raw 33 -> 792.0 мкс.
    """
    setting_no = (addr % 1000) if addr is not None and 1000 <= addr <= 1999 else safe_le16(record, 0)
    layout_name, L = select_setting_layout(record)

    speed = safe_le16(record, int(L["speed_off"]), 5900)
    if not (1000 <= speed <= 10000):
        speed = 5900
    angle = float(safe_le16(record, int(L["angle_off"]), 0))
    freq_raw = safe_u8(record, int(L["freq_off"]))
    freq = freq_raw / float(L["freq_div"])
    probe_time_raw = safe_le16(record, int(L["probe_time_off"]))
    probe_time = probe_time_raw / float(L["probe_time_div"])
    duration_raw = safe_le16(record, int(L["duration_off"]))
    vs1_method = safe_u8(record, int(L["vs1_method_off"]))
    vs2_method = safe_u8(record, int(L["vs2_method_off"]))
    sweep_type_raw = safe_u8(record, int(L["sweep_type_off"]))
    vrch_type_raw = safe_u8(record, int(L["vrch_type_off"]))
    typevar = detect_typevar_code(record, (0x29, 0x2D, 0x3A, 0x3C, 0x40, 0x42), setting_no=setting_no)
    info = typevar_info_643(typevar)
    sdate, stime = best_datetime(record, (int(L.get("date_off", 0)), 0x06, 0x07, 0x08))

    vs1_start = safe_le16(record, int(L["vs1_start_off"]))
    vs1_end = safe_le16(record, int(L["vs1_end_off"]))
    vs2_start = safe_le16(record, int(L["vs2_start_off"]))
    vs2_end = safe_le16(record, int(L["vs2_end_off"]))
    vrch_start = safe_le16(record, int(L["vrch_start_off"]))
    vrch_end = safe_le16(record, int(L["vrch_end_off"]))

    params: dict[str, Any] = {
        "layout": layout_name,
        "setting_no": setting_no,
        "operator_code": "00",
        "date": sdate,
        "time": stime,
        "typevar": typevar_display(typevar),
        "typevar_code": typevar,
        "object": info.get("object", ""),
        "detail": info.get("detail", ""),
        "ntd": info.get("ntd", ""),
        "freq_mhz_raw": freq_raw,
        "freq_mhz": f"{freq:.1f}" if freq else "",
        "sound_speed": speed,
        "probe_no": reverse_digit_field(record, int(L["probe_no_off"]), 6),
        "probe_enabled": "совмещ." if safe_u8(record, 0x0F) == 1 else "-",
        "angle_deg": int(angle),
        "probe_time_raw": probe_time_raw,
        "probe_time_us": f"{probe_time:.2f}",
        "thickness_mm": "0.0",
        "gain_db": safe_u8(record, int(L["gain_off"])),
        "required_sens_db": db_from_negative_byte(safe_u8(record, int(L["required_sens_off"]))),
        "actual_sens_db": db_from_negative_byte(safe_u8(record, int(L["actual_sens_off"]))),
        "extra_gain_db": safe_u8(record, int(L["extra_gain_off"])),
        "extra_gain_enabled": "-",
        "sweep_type_raw": sweep_type_raw,
        "sweep_type": SWEEP_TYPES.get(sweep_type_raw, f"unknown({sweep_type_raw})"),
        "sweep_duration_raw": duration_raw,
        "sweep_duration": format_sweep12(duration_raw, speed, angle),
        "duration_t10": int(round(sweep12_to_time_us(duration_raw) * 10.0)) if duration_raw else 0,
        "w_sweep_enabled": "-",
        "envelope_enabled": "-",

        "vs1_threshold_pct": safe_u8(record, int(L["vs1_thr_off"])),
        "vs1_method_raw": vs1_method,
        "vs1_method": VS1_METHODS.get(vs1_method, f"unknown({vs1_method})"),
        "vs1_start_raw": vs1_start,
        "vs1_start": format_coord13(vs1_start, speed, angle),
        "vs1_end_raw": vs1_end,
        "vs1_end": format_coord13(vs1_end, speed, angle),

        "vs2_threshold_pct": safe_u8(record, int(L["vs2_thr_off"])),
        "vs2_method_raw": vs2_method,
        "vs2_method": VS2_METHODS.get(vs2_method, f"unknown({vs2_method})"),
        "vs2_start_raw": vs2_start,
        "vs2_start": format_coord13(vs2_start, speed, angle),
        "vs2_end_raw": vs2_end,
        "vs2_end": format_coord13(vs2_end, speed, angle),

        "aru_enabled": "-",
        "aru_start": format_coord13(0, speed, angle),
        "aru_end": format_coord13(0, speed, angle),
        "vrch_type_raw": vrch_type_raw,
        "vrch_type": "отключена" if vrch_type_raw == 0 else str(vrch_type_raw),
        "vrch_indication": "-",
        "vrch_start_raw": vrch_start,
        "vrch_start": format_coord13(vrch_start, speed, angle),
        "vrch_end_raw": vrch_end,
        "vrch_end": format_coord13(vrch_end, speed, angle),
        "vrch_amp_db": safe_u8(record, int(L["vrch_amp_off"])),
        "vrch_shape": safe_u8(record, int(L["vrch_shape_off"])),
        "before_vrch_db": safe_u8(record, int(L["before_vrch_off"])),
        "after_vrch_db": safe_u8(record, int(L["after_vrch_off"])),
    }
    return params

def decode_setting_643(record: bytes, addr: int, device_no: Optional[int], strict: bool) -> tuple[dict[str, str], dict[str, Any]]:
    if addr // 1000 != 1:
        raise ValueError(f"not setting addr: {addr}")
    if len(record) < LEN_NASTR2_MIN_DECODE:
        raise ValueError(f"NASTR2 too short even for partial decode: 0x{len(record):X}, need at least 0x{LEN_NASTR2_MIN_DECODE:X}")
    if strict and len(record) > 5 and not is_v643(record, True):
        raise ValueError(f"not 6.43: {fw_string(record)}")
    # V5: частичная настройка всё равно попадает во вкладку “Настройки”.
    # Недоступные поля safe_* заполнят нулями, а params[partial] покажет неполную длину.
    params = decode_nastr2_params_643(record, addr)
    params["partial"] = int(len(record) < LEN_NASTR2)
    params["raw_len"] = len(record)
    params["expected_len"] = LEN_NASTR2
    if len(record) < LEN_NASTR2:
        params["decode_warning"] = f"partial NASTR2: got=0x{len(record):X}, expected=0x{LEN_NASTR2:X}"
    setting_no = addr % 1000
    out = common_meta(record, addr, device_no, "Настройка" + (" (partial)" if len(record) < LEN_NASTR2 else ""), 1000)
    out["KODOPERA"] = "00"
    if params.get("date"):
        out["DATEFORM"] = str(params.get("date", ""))
        out["TIMEFORM"] = str(params.get("time", ""))
    out.update({
        "SETTING_NO": str(setting_no),
        "TYPEVAR": str(params.get("typevar", "")),
        "NUMZAP": "",
    })
    return {c: out.get(c, "") for c in SETTING_COLS}, params


def _score_graph_block(block: bytes) -> int:
    """Heuristic only for choosing among original candidate graph offsets.

    A real A-scan block is 0xF4 bytes around baseline 0x8C with visible
    variation.  Zero/FF/padding blocks score low.  This does not decode data; it
    only chooses between offsets when 6000..6999 extended RESULTS2 adds bytes.
    """
    if len(block) < GRAPH_DRAW_COUNT:
        return -10_000
    samples = block[:GRAPH_DRAW_COUNT]
    uniq = len(set(samples))
    vmin, vmax = min(samples), max(samples)
    near_baseline = sum(1 for b in samples if 0x40 <= b <= 0xF0)
    pad = sum(1 for b in samples if b in (0x00, 0xFF))
    return uniq * 3 + (vmax - vmin) + near_baseline - pad * 4


def find_ascan_graph_offset_643(record: bytes) -> int:
    """Find the 0xF4 A-scan sample block.

    4000..4999 captured frames put graph at tail-0xF4.  PelengPC.exe expects
    6000..6999 as extended RESULTS2 length 0x03A6, so the old fixed 0x1B8
    offset is unsafe there.  Try original candidates and choose the block that
    looks like real A-scan samples.
    """
    if len(record) < GRAPH_COPY_LEN:
        raise ValueError(f"record too short for graph tail: len=0x{len(record):X}, need at least 0x{GRAPH_COPY_LEN:X}")

    candidates: list[int] = []
    # live captures: graph as the final 0xF4 bytes
    candidates.append(len(record) - GRAPH_COPY_LEN)
    # old 4000 short frame fallback
    if len(record) >= GRAPH_OFF + GRAPH_COPY_LEN:
        candidates.append(GRAPH_OFF)
    # nominal zapis2 descriptor working 0x1E5 -> raw-ish 0x1C5; keep as fallback
    for off in (0x1C5, 0x1E5, max(0, len(record) - 0x100 - GRAPH_COPY_LEN)):
        if 0 <= off <= len(record) - GRAPH_COPY_LEN:
            candidates.append(off)

    # de-duplicate preserving order
    seen = set(); uniq = []
    for off in candidates:
        if off not in seen:
            seen.add(off); uniq.append(off)

    best = max(uniq, key=lambda off: _score_graph_block(record[off:off + GRAPH_COPY_LEN]))
    return best


def decode_ascan_graph_643(record: bytes) -> dict[str, Any]:
    off = find_ascan_graph_offset_643(record)
    need = off + GRAPH_COPY_LEN
    if len(record) < need:
        raise ValueError(f"record too short for graph: len=0x{len(record):X}, need=0x{need:X}")
    block = list(record[off:need])
    samples = block[:GRAPH_DRAW_COUNT]
    return {
        "offset": off,
        "copy_len": GRAPH_COPY_LEN,
        "draw_count": min(GRAPH_DRAW_COUNT, len(samples)),
        "baseline": GRAPH_BASELINE,
        "raw_block": block,
        "samples": samples,
        "amplitudes": [s - GRAPH_BASELINE for s in samples],
        "min_sample": min(samples) if samples else None,
        "max_sample": max(samples) if samples else None,
        "line_mode": (safe_u8(record, LINE_FLAG_OFF) & 1) == 0 if len(record) > LINE_FLAG_OFF else True,
        "special_geometry": safe_u8(record, SPECIAL_GEOMETRY_FLAG_OFF) == 3 if len(record) > SPECIAL_GEOMETRY_FLAG_OFF else False,
    }



def duration_t10_from_record(record: bytes) -> int:
    # Verified original type-0x12 duration.  In live 4000+n protocol #4002,
    # duration is setting offset 0x58 shifted to 0xA8.  0xA6 is SO-zone end.
    for off in (0xA8, 0x58, 0x5A):
        dur_raw = safe_le16(record, off)
        if 1 <= dur_raw <= 2000:
            return int(Decimal(str(sweep12_to_time_us(dur_raw) * 10.0)).to_integral_value(rounding=ROUND_HALF_UP))
    return 0

def graph_x_from_raw(raw_x: int, duration_t10: int = 0) -> int:
    if duration_t10 <= 0:
        duration_t10 = 7920  # 6.42/6.43 common fallback from XML sample
    return int(Decimal(str(raw_x * GRAPH_WIDTH_ORIG / duration_t10)).to_integral_value(rounding=ROUND_HALF_UP))


def decode_ascan_zones_643(record: bytes) -> dict[str, Any]:
    speed = safe_le16(record, 0x77, 5900)
    angle = 0.0
    vs1_start = safe_le16(record, VS1_START_OFF)
    vs1_end = safe_le16(record, VS1_END_OFF)
    vs2_start = safe_le16(record, VS2_START_OFF)
    vs2_end = safe_le16(record, VS2_END_OFF)
    extra_start = safe_le16(record, EXTRA_START_OFF)
    extra_end = safe_le16(record, EXTRA_END_OFF)
    vs1_method = safe_u8(record, VS1_METHOD_OFF)
    vs2_method = safe_u8(record, VS2_METHOD_OFF)
    duration_t10 = duration_t10_from_record(record)
    return {
        "setting_no": protocol_setting_no_643(record),
        "duration_t10": duration_t10,
        "vs1_threshold": safe_u8(record, VS1_THRESHOLD_OFF),
        "vs1_method_raw": vs1_method,
        "vs1_method": VS1_METHODS.get(vs1_method, f"unknown({vs1_method})"),
        "vs1_start_raw": vs1_start,
        "vs1_start": format_coord13(vs1_start, speed, angle),
        "vs1_end_raw": vs1_end,
        "vs1_end": format_coord13(vs1_end, speed, angle),
        "vs1_start_px": graph_x_from_raw(vs1_start, duration_t10),
        "vs1_end_px": graph_x_from_raw(vs1_end, duration_t10),
        "vs2_threshold": safe_u8(record, VS2_THRESHOLD_OFF),
        "vs2_method_raw": vs2_method,
        "vs2_method": VS2_METHODS.get(vs2_method, f"unknown({vs2_method})"),
        "vs2_start_raw": vs2_start,
        "vs2_start": format_coord13(vs2_start, speed, angle),
        "vs2_end_raw": vs2_end,
        "vs2_end": format_coord13(vs2_end, speed, angle),
        "vs2_start_px": graph_x_from_raw(vs2_start, duration_t10),
        "vs2_end_px": graph_x_from_raw(vs2_end, duration_t10),
        "extra_start_raw": extra_start,
        "extra_start": format_coord13(extra_start, speed, angle),
        "extra_end_raw": extra_end,
        "extra_end": format_coord13(extra_end, speed, angle),
        "extra_start_px": graph_x_from_raw(extra_start, duration_t10),
        "extra_end_px": graph_x_from_raw(extra_end, duration_t10),
    }

def fw_code_643(record: bytes) -> int:
    return safe_le16(record, 0x04, 0)



def zones_from_setting_record_643(record: bytes) -> dict[str, int]:
    _layout_name, L = select_setting_layout(record)
    return {
        "vs1_threshold": safe_u8(record, int(L["vs1_thr_off"])),
        "vs1_method_raw": safe_u8(record, int(L["vs1_method_off"])),
        "vs1_start_raw": safe_le16(record, int(L["vs1_start_off"])),
        "vs1_end_raw": safe_le16(record, int(L["vs1_end_off"])),
        "vs2_threshold": safe_u8(record, int(L["vs2_thr_off"])),
        "vs2_method_raw": safe_u8(record, int(L["vs2_method_off"])),
        "vs2_start_raw": safe_le16(record, int(L["vs2_start_off"])),
        "vs2_end_raw": safe_le16(record, int(L["vs2_end_off"])),
    }

def diagnose_protocol_643(addr: int, protocol_record: bytes, graph_record: Optional[bytes], setting_record: Optional[bytes]) -> dict[str, Any]:
    warnings: list[str] = []
    expected_protocol_len = expected_len_for_addr(addr) or len(protocol_record)
    if len(protocol_record) < expected_protocol_len:
        warnings.append(f"protocol_short: got=0x{len(protocol_record):X}, expected=0x{expected_protocol_len:X}")

    fw = fw_code_643(protocol_record)
    if fw not in SUPPORTED_FW_CODES:
        warnings.append(f"unexpected_fw_code: 0x{fw:04X}; expected 0x2A06/0x2B06")

    setting_no = protocol_setting_no_643(protocol_record)
    setting_addr = 1000 + setting_no if 0 < setting_no <= 999 else 0
    if not (0 < setting_no <= 999):
        warnings.append(f"bad_setting_no: {setting_no}")

    linked_graph_addr = graph_addr_for_protocol(addr) if 4000 <= addr <= 6999 else 0
    graph_found = graph_record is not None
    graph_len = len(graph_record or b"")
    if linked_graph_addr and not graph_found:
        warnings.append(f"linked_graph_missing: {linked_graph_addr}")
    elif graph_record is not None:
        need = GRAPH_OFF + GRAPH_COPY_LEN
        if len(graph_record) < need:
            warnings.append(f"graph_short: got=0x{len(graph_record):X}, need=0x{need:X}")

    setting_found = setting_record is not None
    if setting_addr and not setting_found:
        warnings.append(f"setting_missing: {setting_addr}")

    zones_match: Optional[bool] = None
    if graph_record is not None and setting_record is not None:
        gz = decode_ascan_zones_643(graph_record)
        sz = zones_from_setting_record_643(setting_record)
        strict_keys = [
            "vs1_threshold", "vs1_method_raw", "vs1_start_raw", "vs1_end_raw",
            "vs2_threshold", "vs2_method_raw", "vs2_start_raw", "vs2_end_raw",
        ]
        zones_match = all(int(gz.get(k, -999999)) == int(sz.get(k, -999998)) for k in strict_keys)
        if not zones_match:
            warnings.append("zones_differ_from_current_setting_snapshot")

    special = bool(graph_record and len(graph_record) > SPECIAL_GEOMETRY_FLAG_OFF and graph_record[SPECIAL_GEOMETRY_FLAG_OFF] == 3)
    if special:
        warnings.append("special_geometry_flag_record_0xF0_eq_3")

    return {
        "address": addr,
        "linked_graph_addr": linked_graph_addr,
        "setting_addr": setting_addr,
        "fw_code": f"0x{fw:04X}",
        "record_len": len(protocol_record),
        "graph_found": int(graph_found),
        "graph_len": graph_len,
        "setting_found": int(setting_found),
        "setting_no": setting_no,
        "zones_match_setting": None if zones_match is None else int(zones_match),
        "special_geometry": int(special),
        "warnings": warnings,
        "warnings_json": json.dumps(warnings, ensure_ascii=False),
    }


@dataclass
class SerialConfig:
    port: str
    baud: int = DEFAULT_BAUD
    bytesize: int = DEFAULT_BYTESIZE
    parity: str = DEFAULT_PARITY
    stopbits: int = DEFAULT_STOPBITS
    inter_byte_gap: float = DEFAULT_INTER_BYTE_GAP
    first_timeout: float = DEFAULT_FIRST_BYTE_TIMEOUT
    body_timeout: float = DEFAULT_BODY_TIMEOUT
    timing_profile: bool = DEFAULT_TIMING_PROFILE
    timing_byte_mode: bool = DEFAULT_TIMING_BYTE_MODE
    command_cooldown: float = DEFAULT_COMMAND_COOLDOWN


@dataclass
class SerialTimingSample:
    created_at: str
    cmd: str
    addr: Optional[int]
    kind: str
    expected: int
    raw_len: int
    first_byte_ms: float
    total_ms: float
    max_gap_ms: float
    p95_gap_ms: float
    gaps_over_10ms: int
    declared_len: int
    prefix_off: int
    status: str
    preview_hex: str


def _percentile(values: list[float], pct: float) -> float:
    vals = sorted(v for v in values if v is not None and v >= 0)
    if not vals:
        return 0.0
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    if f == c:
        return vals[f]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def infer_response_prefix(resp: bytes, addr: Optional[int]) -> tuple[int, int]:
    """Return (prefix_off, declared_len) for a 0x42 response when possible.

    UD2102base determines completion from rx[2:4] regardless of whether rx[0:2]
    is the requested address.  Some live report bodies are body-only, so the
    requested addr is not always present at offset 0.
    """
    if len(resp) < 4:
        return -1, 0
    if addr is not None:
        max_off = min(0x40, len(resp) - 3)
        for off in range(max_off):
            if safe_le16(resp, off, -1) == addr:
                return off, safe_le16(resp, off + 2, 0)
    declared = safe_le16(resp, 2, 0)
    if 0 < declared <= 0x1200:
        return 0, declared
    return -1, 0


def peleng_checksum_ok(resp: bytes, declared_len: int = 0) -> Optional[bool]:
    """UD2102base check: sum(frame bytes) & 0xFF must be 0xFF."""
    if not resp or len(resp) < 4 or is_empty_payload(resp):
        return None
    n = declared_len or safe_le16(resp, 2, 0)
    if n <= 0 or len(resp) < n:
        return None
    return (sum(resp[:n]) & 0xFF) == 0xFF


def timing_status(resp: bytes, addr: Optional[int], expected: int) -> tuple[str, int, int]:
    prefix_off, declared_len = infer_response_prefix(resp, addr)
    if not resp:
        return "no_first_byte", prefix_off, declared_len
    if is_empty_payload(resp):
        return "empty_payload", prefix_off, declared_len
    # Round29 strict mode: SHORTPROT2 is accepted as OK only when the
    # structural report validator sees <addr><len> and the complete declared
    # length.  Older 0x52..0x55 partial frames are now classified below as
    # short/bad rather than silently counted as good reports.
    if addr is not None and 10000 <= addr <= 29999 and report_wire_complete(resp, addr):
        return "ok_shortprot2_struct", prefix_off, report_wire_declared_len(resp)
    if declared_len and len(resp) < declared_len:
        return "short_vs_declared", prefix_off, declared_len
    chk = peleng_checksum_ok(resp, declared_len)
    if chk is False:
        return "checksum_bad", prefix_off, declared_len
    if expected and len(resp) < expected:
        return "short_vs_expected", prefix_off, declared_len
    if expected and len(resp) > expected:
        return ("longer_than_expected" if chk is None else "ok_checksum"), prefix_off, declared_len
    return ("ok_checksum" if chk is True else "ok"), prefix_off, declared_len


class TimingProfiler:
    """Collects empirical serial timings from the real Peleng device.

    It is intentionally file/CSV based rather than hidden in SQLite: timings are
    a transport-level artifact and should be attached to bug reports together
    with RAW ZIPs.
    """

    def __init__(self) -> None:
        self.samples: list[SerialTimingSample] = []

    def add(self, sample: SerialTimingSample) -> None:
        self.samples.append(sample)

    def __len__(self) -> int:
        return len(self.samples)

    def export_csv(self, path: str) -> None:
        fields = [
            "created_at", "cmd", "addr", "kind", "expected", "raw_len",
            "first_byte_ms", "total_ms", "max_gap_ms", "p95_gap_ms",
            "gaps_over_10ms", "declared_len", "prefix_off", "status", "preview_hex",
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, delimiter=";")
            writer.writeheader()
            for smp in self.samples:
                writer.writerow({k: getattr(smp, k) for k in fields})

    def summary_rows(self) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str], list[SerialTimingSample]] = {}
        for smp in self.samples:
            groups.setdefault((smp.cmd, smp.kind), []).append(smp)
        rows: list[dict[str, Any]] = []
        for (cmd, kind), arr in sorted(groups.items()):
            nonempty = [x for x in arr if x.raw_len > 0]
            firsts = [x.first_byte_ms for x in nonempty if x.first_byte_ms >= 0]
            totals = [x.total_ms for x in nonempty if x.total_ms >= 0]
            gaps = [x.max_gap_ms for x in nonempty if x.max_gap_ms >= 0]
            rows.append({
                "cmd": cmd,
                "kind": kind,
                "count": len(arr),
                "nonempty": len(nonempty),
                "empty": len(arr) - len(nonempty),
                "short": sum(1 for x in arr if x.status.startswith("short")),
                "p95_first_ms": _percentile(firsts, 95),
                "p99_first_ms": _percentile(firsts, 99),
                "p95_total_ms": _percentile(totals, 95),
                "p99_total_ms": _percentile(totals, 99),
                "p95_max_gap_ms": _percentile(gaps, 95),
                "p99_max_gap_ms": _percentile(gaps, 99),
                "max_gap_ms": max(gaps) if gaps else 0.0,
            })
        return rows

    def recommended_timeouts(self) -> dict[str, float]:
        nonempty = [x for x in self.samples if x.raw_len > 0]
        firsts = [x.first_byte_ms for x in nonempty if x.first_byte_ms >= 0]
        max_gaps = [x.max_gap_ms for x in nonempty if x.max_gap_ms >= 0]
        totals = [x.total_ms for x in nonempty if x.total_ms >= 0]
        p99_first = _percentile(firsts, 99) / 1000.0
        p99_gap = _percentile(max_gaps, 99) / 1000.0
        p99_total = _percentile(totals, 99) / 1000.0
        # We keep margins intentionally conservative: the real device can pause
        # between logical blocks, and Windows USB-serial drivers add jitter.
        return {
            "first_timeout": round(min(max(p99_first * 2.0 + 0.05, 0.08), 1.50), 3),
            "body_timeout": round(min(max(p99_gap * 2.5 + 0.015, 0.025), 0.35), 3),
            "extra_drain_timeout": round(min(max(p99_gap * 1.5 + 0.02, 0.03), 0.25), 3),
            "request_total_timeout": round(min(max(p99_total + 0.50, 1.00), 8.00), 3),
            "command_cooldown": DEFAULT_COMMAND_COOLDOWN,
        }


class PelengSerial:
    def __init__(self, cfg: SerialConfig):
        if serial is None:
            raise RuntimeError("pyserial не установлен: python -m pip install pyserial")
        self.cfg = cfg
        self.ser = serial.Serial(
            port=cfg.port,
            baudrate=cfg.baud,
            bytesize=cfg.bytesize,
            parity=cfg.parity,  # round44 live-sniffer/device test: parity E gives stable 218 report Idx
            stopbits=cfg.stopbits,
            timeout=cfg.first_timeout,
            write_timeout=1.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        # Round46: do not touch DTR/RTS at all.  Earlier builds forced them
        # low, then high; both are extra behaviour not present in the reversed
        # exchange path.  Leave pyserial/driver defaults unchanged.
        # PelengPC path: after opening COM the original code lets the adapter settle.
        time.sleep(0.1)
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception:
            pass
        self.timing = TimingProfiler() if cfg.timing_profile else None
        self._report_seen_nonempty = False

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def _write_bytes_slow(self, data: bytes) -> None:
        for b in data:
            self.ser.write(bytes([b]))
            self.ser.flush()
            if self.cfg.inter_byte_gap > 0:
                time.sleep(self.cfg.inter_byte_gap)  # v25: emulate original GetTickCount-based Sleep(10) on old Windows

    def _add_timing_sample(self, cmd: str, addr: Optional[int], expected: int, start: float, first_at: Optional[float],
                           end: float, resp: bytes, byte_times: list[float]) -> None:
        if self.timing is None:
            return
        gaps_ms: list[float] = []
        if len(byte_times) > 1:
            gaps_ms = [(b - a) * 1000.0 for a, b in zip(byte_times, byte_times[1:])]
        status, prefix_off, declared_len = timing_status(resp, addr, expected)
        kind = kind_for_addr(addr) if addr is not None else "handshake55"
        self.timing.add(SerialTimingSample(
            created_at=dt.datetime.now().isoformat(timespec="milliseconds"),
            cmd=cmd,
            addr=addr,
            kind=kind,
            expected=int(expected or 0),
            raw_len=len(resp),
            first_byte_ms=round(((first_at - start) * 1000.0), 3) if first_at is not None else -1.0,
            total_ms=round(((end - start) * 1000.0), 3),
            max_gap_ms=round(max(gaps_ms), 3) if gaps_ms else 0.0,
            p95_gap_ms=round(_percentile(gaps_ms, 95), 3) if gaps_ms else 0.0,
            gaps_over_10ms=sum(1 for g in gaps_ms if g > 10.0),
            declared_len=declared_len,
            prefix_off=prefix_off,
            status=status,
            preview_hex=resp[:32].hex(" "),
        ))

    def read_until_quiet_profiled(self, cmd: str, addr: Optional[int], expected_size: int,
                                  first_timeout: float, quiet_timeout: float, max_bytes: int = 8192) -> bytes:
        """Byte-by-byte reader used for reverse-engineering real device delays.

        This deliberately reads one byte at a time so we can measure gaps between
        bytes/blocks. It is slower than chunk mode but preserves the critical
        timing facts needed to tune first/body/extra timeouts.
        """
        old_timeout = self.ser.timeout
        start = time.perf_counter()
        first_at: Optional[float] = None
        times: list[float] = []
        out = bytearray()
        hard_deadline = start + max(DEFAULT_REQUEST_TOTAL_TIMEOUT, expected_size / 1000.0 + 1.0)
        try:
            self.ser.timeout = max(first_timeout, 0.03)
            b = self.ser.read(1)
            if not b:
                end = time.perf_counter()
                self._add_timing_sample(cmd, addr, expected_size, start, None, end, b"", times)
                return b""
            first_at = time.perf_counter()
            out.extend(b)
            times.append(first_at)

            # Use the configured quiet timeout as the exact boundary of a logical response.
            # For short/empty debugging, never clamp below 2 ms; for Windows this still
            # acts as an approximate per-byte silence detector.
            self.ser.timeout = max(quiet_timeout, 0.002)
            while len(out) < max_bytes and time.perf_counter() < hard_deadline:
                b = self.ser.read(1)
                if not b:
                    break
                now = time.perf_counter()
                out.extend(b)
                times.append(now)
                # Empty markers FD FF / FF FF are complete two-byte answers; do not
                # wait the full body timeout for thousands of empty addresses.
                if len(out) == 2 and bytes(out) in (b"\xfd\xff", b"\xff\xff"):
                    break
                # After expected bytes we still allow a tiny drain: some responses
                # declare one size but have a short late tail.
                if expected_size and len(out) >= expected_size:
                    self.ser.timeout = max(min(DEFAULT_EXTRA_DRAIN_TIMEOUT, quiet_timeout), 0.002)

            end = time.perf_counter()
            resp = bytes(out)
            self._add_timing_sample(cmd, addr, expected_size, start, first_at, end, resp, times)
            return resp
        finally:
            self.ser.timeout = old_timeout

    def read_until_ff_ff(self, first_timeout: float, total_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT, max_bytes: int = 8192) -> bytes:
        """Read the 0x55 catalogue answer like PelengPC.exe.

        Important correction for report-heavy catalogues:
        PelengPC.exe does NOT stop 0x55 on the first FF FF / FD FF marker.
        It sends one byte 55 and calls the same COM helper in direct mode,
        reading until the line is quiet, then it
        drops only the final WORD as a guard. Live screenshots from the native
        program show a large 55 catalogue split into log chunks about 0.35 s
        apart and COM closing about another 0.34 s later, so the Python guard
        uses a conservative 0.65 s inactivity timeout for 55 only. Some real catalogues contain
        several report runs and marker-looking words before the physical end;
        stopping early loses later >10000 report Idx entries.
        """
        old_timeout = self.ser.timeout
        start = time.perf_counter()
        first_at: Optional[float] = None
        times: list[float] = []
        out = bytearray()
        hard_deadline = start + max(total_timeout, 0.5)
        try:
            # Wait for the first byte of the catalogue. This can be relatively
            # slow after opening the port/55, so keep the user-configured guard.
            self.ser.timeout = max(first_timeout, 0.05)
            first = self.ser.read(1)
            if not first:
                end = time.perf_counter()
                self._add_timing_sample("55", None, 0, start, None, end, b"", times)
                return b""
            out.extend(first)
            first_at = time.perf_counter()
            times.append(first_at)

            # Direct silence-read: do not stop on FF FF. Read available chunks
            # until a conservative catalogue inactivity timeout after the latest
            # chunk, or hard deadline.  Do NOT reuse this long timeout for 42.
            self.ser.timeout = ORIGINAL_55_SILENCE_TIMEOUT
            while len(out) < max_bytes and time.perf_counter() < hard_deadline:
                chunk = self.ser.read(min(ORIGINAL_RX_CHUNK_MAX, max_bytes - len(out)))
                if not chunk:
                    break
                now = time.perf_counter()
                out.extend(chunk)
                for i in range(len(chunk)):
                    times.append(now + i * 0.000001)
                # After each successful block the original helper effectively
                # extends the silence deadline; pyserial timeout already models
                # this because every read() waits for a fresh timeout.
                self.ser.timeout = ORIGINAL_55_SILENCE_TIMEOUT

            end = time.perf_counter()
            resp = bytes(out)
            self._add_timing_sample("55", None, 0, start, first_at, end, resp, times)
            return resp
        finally:
            self.ser.timeout = old_timeout

    def read_frame_len_2_3(self, addr: int, expected_size: int, started_at: float, max_bytes: int = 16384) -> bytes:
        """Read a 0x42 response in the corrected PelengPC receiver model.

        Round35 reverse correction:
        PelengPC.exe:0x411810 is an OnRxChar handler. It is called when the
        serial driver reports received characters; the program then reads the
        available block up to 0x400 bytes. It is NOT a Python-style polling loop
        that performs an empty read every 8 ms.  The earlier emulation created
        artificial short frames: 85/86 could be finalized before the final
        checksum byte had a chance to arrive.

        This reader therefore does one original 42 request and then waits for
        expected_len_for_addr(ID) in the same request.  No new 42 is sent.  If
        the frame is still short after the body/last-byte wait, it is returned
        as diagnostic raw and rejected by the decoder, matching the original
        actual_len != expected_len check.
        """
        old_timeout = self.ser.timeout
        first_at: Optional[float] = None
        times: list[float] = []
        out = bytearray()
        target_len = expected_size or 0
        if target_len <= 0:
            target_len = 4
        target_len = min(target_len, max_bytes)
        # At 19200 baud 0x0FD6 takes ~2.3 s on the wire.  Keep a safety guard,
        # but do not use it as an inter-byte delimiter.
        hard_deadline = started_at + max(
            DEFAULT_REQUEST_TOTAL_TIMEOUT,
            (max(target_len, 1) * 11.0 / max(self.cfg.baud, 1200)) + 2.0,
        )

        def stamp(n: int) -> None:
            now = time.perf_counter()
            nonlocal first_at
            if first_at is None:
                first_at = now
            for i in range(n):
                times.append(now + i * 0.000001)

        try:
            # First byte: if the address is really empty, this should fail fast.
            self.ser.timeout = max(self.cfg.first_timeout, 0.05)
            first = self.ser.read(1)
            if not first:
                end = time.perf_counter()
                self._add_timing_sample("42", addr, expected_size, started_at, None, end, b"", times)
                return b""
            out.extend(first)
            stamp(1)

            # FD FF / FF FF is a complete empty marker.
            self.ser.timeout = ORIGINAL_RX_BODY_TIMEOUT
            if len(out) == 1:
                b2 = self.ser.read(1)
                if b2:
                    out.extend(b2)
                    stamp(len(b2))
                    if bytes(out) in (b"\xfd\xff", b"\xff\xff"):
                        end = time.perf_counter()
                        resp = bytes(out)
                        self._add_timing_sample("42", addr, expected_size, started_at, first_at, end, resp, times)
                        return resp

            # Main body: read in chunks up to 0x400 like original ReadFile path,
            # but wait for the expected frame rather than inventing idle events.
            while len(out) < target_len and time.perf_counter() < hard_deadline:
                need = min(ORIGINAL_RX_CHUNK_MAX, target_len - len(out))
                self.ser.timeout = ORIGINAL_RX_BODY_TIMEOUT
                chunk = self.ser.read(need)
                if not chunk:
                    break
                out.extend(chunk)
                stamp(len(chunk))

            # The recurring live failure is 0x55/0x56: only checksum byte is late.
            # Same request, no retry.  Wait specifically for the missing byte(s).
            if 0 < len(out) < target_len and not is_wire_empty_marker(out):
                late_deadline = time.perf_counter() + ORIGINAL_RX_LATE_TAIL_TIMEOUT
                while len(out) < target_len and time.perf_counter() < late_deadline:
                    self.ser.timeout = min(0.200, max(0.050, late_deadline - time.perf_counter()))
                    chunk = self.ser.read(min(ORIGINAL_RX_CHUNK_MAX, target_len - len(out)))
                    if chunk:
                        out.extend(chunk)
                        stamp(len(chunk))

            # Tiny drain only after finalizing a still-short diagnostic frame, so
            # delayed junk does not become the prefix of the next address.  Do not
            # append beyond expected_len: original caller compares actual length.
            if 0 < len(out) < target_len and not is_wire_empty_marker(out):
                drain_deadline = time.perf_counter() + ORIGINAL_RX_SHORT_DRAIN_TIMEOUT
                while len(out) < target_len and time.perf_counter() < drain_deadline:
                    self.ser.timeout = 0.050
                    chunk = self.ser.read(min(ORIGINAL_RX_CHUNK_MAX, target_len - len(out)))
                    if chunk:
                        out.extend(chunk)
                        stamp(len(chunk))

            end = time.perf_counter()
            resp = bytes(out)
            self._add_timing_sample("42", addr, expected_size, started_at, first_at, end, resp, times)
            return resp
        finally:
            self.ser.timeout = old_timeout

    def read_until_quiet(self, first_timeout: float, quiet_timeout: float, max_bytes: int = 8192) -> bytes:
        if self.timing is not None and self.cfg.timing_byte_mode:
            return self.read_until_quiet_profiled("55", None, 0, first_timeout, quiet_timeout, max_bytes)
        old_timeout = self.ser.timeout
        try:
            self.ser.timeout = first_timeout
            first = self.ser.read(1)
            if not first:
                return b""
            out = bytearray(first)
            self.ser.timeout = quiet_timeout
            while len(out) < max_bytes:
                chunk = self.ser.read(min(256, max_bytes - len(out)))
                if not chunk:
                    break
                out.extend(chunk)
            return bytes(out)
        finally:
            self.ser.timeout = old_timeout

    def read_expected_or_timeout(self, expected_size: int, first_timeout: float, quiet_timeout: float) -> bytes:
        """
        Быстрое чтение ответа 0x42 для живого УД2-102/103.

        Важно: прибор часто объявляет полный размер в raw[2:4], например 0x02B6,
        но фактически отдаёт на 10-12 байт меньше. Старый алгоритм ждал
        недостающий хвост до общего timeout, из-за чего чтение сотен записей
        занимало очень долго.

        Новая логика:
        - если вообще нет первого байта — быстро считаем адрес пустым;
        - если данные пошли — читаем пока поток непрерывный;
        - как только наступила устойчивая тишина quiet_timeout, возвращаем
          частичный raw и сохраняем его.
        """
        old_timeout = self.ser.timeout
        max_bytes = max(expected_size + 0x40, 256)
        hard_deadline = time.monotonic() + max(DEFAULT_REQUEST_TOTAL_TIMEOUT, expected_size / 1200.0 + 0.8)
        try:
            self.ser.timeout = max(first_timeout, 0.03)
            first = self.ser.read(1)
            if not first:
                return b""

            out = bytearray(first)
            self.ser.timeout = max(quiet_timeout, 0.025)

            while len(out) < expected_size and len(out) < max_bytes and time.monotonic() < hard_deadline:
                need = min(512, expected_size - len(out))
                chunk = self.ser.read(max(1, need))
                if not chunk:
                    # Устойчивая тишина: считаем ответ завершённым, даже если он
                    # короче объявленного размера. Это нормально для live RAW.
                    break
                out.extend(chunk)

            # Короткий добор совсем мелкого хвоста, если он уже лежит в буфере.
            if len(out) < max_bytes:
                self.ser.timeout = DEFAULT_EXTRA_DRAIN_TIMEOUT
                chunk = self.ser.read(min(256, max_bytes - len(out)))
                if chunk:
                    out.extend(chunk)

            return bytes(out)
        finally:
            self.ser.timeout = old_timeout

    def drain_stale_input(self, quiet_timeout: float = BAD_PREFIX_DRAIN_TIMEOUT, max_total: float = 0.60) -> int:
        """Drain delayed tail bytes from a previous Peleng response.

        The real device sometimes sends a late tail after a short/truncated read.
        If we immediately send the next 0x42, those late bytes become the first
        bytes of the next address and produce false settings/reports.
        """
        old_timeout = self.ser.timeout
        drained = 0
        deadline = time.monotonic() + max_total
        try:
            self.ser.timeout = max(quiet_timeout, 0.01)
            while time.monotonic() < deadline:
                chunk = self.ser.read(256)
                if not chunk:
                    break
                drained += len(chunk)
            return drained
        finally:
            self.ser.timeout = old_timeout


    def handshake55(self, count: int = DEFAULT_HANDSHAKE_COUNT) -> bytes:
        # UD2102base.exe sends exactly one 0x55.  Multiple 55 bytes concatenate
        # replies and destroy the fixed offset-0x10 ID list, so count is ignored
        # intentionally in this 1:1 timing profile.
        self.ser.reset_input_buffer()
        self.ser.write(b"\x55")
        self.ser.flush()
        return self.read_until_ff_ff(DEFAULT_HANDSHAKE_TIMEOUT, DEFAULT_HANDSHAKE_TIMEOUT, ORIGINAL_55_MAX_BYTES)

    def _write_42_command_original(self, addr: int) -> float:
        """Send 42 LL HH byte-by-byte as PelengPC.exe: 10 ms gap by default."""
        # PelengPC.exe:0x424CC0 does not purge the input buffer before every
        # 42.  Purging here can discard the late checksum byte that caused
        # repeated 0x55/85-byte report frames.  Handshake still purges before 55.
        cmd = bytes([0x42, addr & 0xFF, (addr >> 8) & 0xFF])
        start = time.perf_counter()
        for b in cmd:
            self.ser.write(bytes([b]))
            self.ser.flush()
            time.sleep(self.cfg.inter_byte_gap)  # v25: emulate original GetTickCount-based Sleep(10) on old Windows
        return start

    def read_shortprot2_champion(self, addr: int, started_at: float) -> bytes:
        """Structural SHORTPROT2 reader for reports.

        PLG reverse showed the native program stores report buckets as
        16-byte PLG header + 100 slots. Each non-empty slot begins with
        <addr><len> and, for the uploaded BNEW report bucket, len=0x56.
        Therefore we now read the 4-byte report header first, then wait for
        exactly the declared length. If only 0x52..0x55 bytes arrive while
        declared len is 0x56, the response is retried by fetch_record().
        """
        old_timeout = self.ser.timeout
        first_at: Optional[float] = None
        times: list[float] = []
        out = bytearray()

        def append_timed(chunk: bytes) -> None:
            nonlocal first_at
            if not chunk:
                return
            now = time.perf_counter()
            if first_at is None:
                first_at = now
            out.extend(chunk)
            if len(chunk) == 1:
                times.append(now)
            else:
                for i in range(len(chunk)):
                    times.append(now + i * 0.000001)

        try:
            self.ser.timeout = REPORT_TAIL_TIMEOUT if self._report_seen_nonempty else REPORT_HEAD_TIMEOUT
            head = self.ser.read(2)
            append_timed(head)
            if not head or bytes(head) in (b"\xfd\xff", b"\xff\xff"):
                end = time.perf_counter()
                self._add_timing_sample("42", addr, LEN_SHORTPROT2, started_at, first_at, end, bytes(out), times)
                return bytes(out)

            self._report_seen_nonempty = True
            self.ser.timeout = REPORT_TAIL_TIMEOUT

            # Read the length word. Without it we cannot know whether 0x52..0x55
            # is a real short frame or a truncated 0x56 frame.
            if len(out) < 4:
                append_timed(self.ser.read(4 - len(out)))

            target_len = report_wire_declared_len(out)
            # Bad prefix/length is still read up to 0x56 for forensic export,
            # then fetch_record() will drain+retry.
            if len(out) >= 4 and safe_le16(out, 0, -1) != addr:
                target_len = LEN_SHORTPROT2

            deadline = started_at + max(0.85, (target_len * 11.0 / max(self.cfg.baud, 1200)) + 0.45)
            while len(out) < target_len and time.perf_counter() < deadline:
                need = max(1, target_len - len(out))
                chunk = self.ser.read(need)
                if not chunk:
                    # Keep waiting until the hard structural deadline. This is
                    # slower only for broken reads, but prevents 82..85 byte RAW.
                    self.ser.timeout = max(REPORT_TAIL_TIMEOUT, 0.05)
                    continue
                append_timed(chunk)

            # If bytes are already buffered, take only the missing part of this
            # frame. Anything beyond it belongs to stale noise and will be drained
            # before retry if the frame is still invalid.
            try:
                waiting = getattr(self.ser, "in_waiting", 0)
            except Exception:
                waiting = 0
            if waiting and len(out) < target_len:
                append_timed(self.ser.read(min(target_len - len(out), waiting)))

            end = time.perf_counter()
            self._add_timing_sample("42", addr, LEN_SHORTPROT2, started_at, first_at, end, bytes(out), times)
            return bytes(out)
        finally:
            self.ser.timeout = old_timeout

    def read_short_record_fast(self, addr: int, expected_size: int, started_at: float) -> bytes:
        """Fast benchmark-derived reader for fixed 0x56 report frames.

        This path is tuned from the user's 218-report benchmark (222.zip):
        profile p0033_g004_cd003_f060_s035_t0450, which collected 218/218
        exact report payloads in about 28.5 s.  It uses a non-blocking
        in_waiting loop instead of serial.read(timeout=...) waits, so it does
        not burn 60 ms on every empty body read.
        """
        old_timeout = self.ser.timeout
        first_at: Optional[float] = None
        times: list[float] = []
        out = bytearray()
        extra = bytearray()
        target_len = expected_size or LEN_SHORTPROT2
        deadline = started_at + FAST_REPORT_TOTAL_TIMEOUT
        last_rx_at: Optional[float] = None

        def append_timed(chunk: bytes) -> None:
            nonlocal first_at, last_rx_at
            if not chunk:
                return
            now = time.perf_counter()
            if first_at is None:
                first_at = now
            last_rx_at = now
            out.extend(chunk)
            if len(chunk) == 1:
                times.append(now)
            else:
                for i in range(len(chunk)):
                    times.append(now + i * 0.000001)

        try:
            # Non-blocking polling; benchmark showed this is both faster and stable
            # for the 218 SHORTPROT2 report set at 19200 8E1.
            self.ser.timeout = 0
            while time.perf_counter() < deadline:
                waiting = 0
                try:
                    waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
                except Exception:
                    waiting = 0

                if waiting:
                    need = max(1, min(waiting, target_len - len(out), ORIGINAL_RX_CHUNK_MAX))
                    chunk = self.ser.read(need)
                    if chunk:
                        append_timed(chunk)
                        if len(out) >= target_len:
                            break
                        continue

                now = time.perf_counter()
                if not out and (now - started_at) >= FAST_REPORT_FIRST_TIMEOUT:
                    break
                if out and last_rx_at is not None and (now - last_rx_at) >= FAST_REPORT_BODY_TIMEOUT:
                    break
                time.sleep(FAST_REPORT_POLL_INTERVAL)

            # Tiny post-expected drain, only to prevent stale bytes from poisoning
            # the next request. Extra bytes are not appended to the main frame.
            if len(out) >= target_len and FAST_REPORT_DRAIN_AFTER_EXPECTED > 0:
                end_drain = time.perf_counter() + FAST_REPORT_DRAIN_AFTER_EXPECTED
                while time.perf_counter() < end_drain:
                    waiting = 0
                    try:
                        waiting = int(getattr(self.ser, "in_waiting", 0) or 0)
                    except Exception:
                        waiting = 0
                    if waiting:
                        extra.extend(self.ser.read(waiting))
                    else:
                        time.sleep(FAST_REPORT_POLL_INTERVAL)

            end = time.perf_counter()
            resp = bytes(out[:target_len]) if len(out) >= target_len else bytes(out)
            # If there were unexpected bytes, timing status will still be based on
            # the main frame; stale bytes are deliberately drained, not decoded.
            self._add_timing_sample("42", addr, expected_size, started_at, first_at, end, resp, times)
            return resp
        finally:
            self.ser.timeout = old_timeout

    def _request42_report_fast(self, addr: int, expected_size: int) -> bytes:
        """Send 42 LL HH with the best 218-report timing profile."""
        if FAST_REPORT_COMMAND_COOLDOWN > 0:
            time.sleep(FAST_REPORT_COMMAND_COOLDOWN)
        cmd = bytes([0x42, addr & 0xFF, (addr >> 8) & 0xFF])
        start = time.perf_counter()
        for b in cmd:
            self.ser.write(bytes([b]))
            self.ser.flush()
            time.sleep(FAST_REPORT_INTER_BYTE_GAP)
        if FAST_REPORT_COMMAND_COOLDOWN > 0:
            time.sleep(FAST_REPORT_COMMAND_COOLDOWN)
        return self.read_short_record_fast(addr, expected_size, start)

    def request42_raw(self, addr: int, expected_size: int) -> bytes:
        # Round29: one original transport path for all record classes.
        # Fast collection mode: reports are fixed 0x56 frames and dominate the
        # user workflow (218 records on the current device). Use the measured
        # 218-report benchmark profile instead of the slower diagnostic reader.
        if FAST_REPORT_READER and expected_size == LEN_SHORTPROT2 and kind_for_addr(addr) in ("report", "report_v2"):
            return self._request42_report_fast(addr, expected_size)

        # Safe fallback for protocols/settings/B-scan: keep the original-like
        # command timing and structural reader.
        if self.cfg.command_cooldown > 0:
            time.sleep(self.cfg.command_cooldown)
        start = self._write_42_command_original(addr)
        if self.cfg.command_cooldown > 0:
            steps = 15
            per_step = self.cfg.command_cooldown / steps
            for _ in range(steps):
                time.sleep(per_step)
        return self.read_frame_len_2_3(addr, expected_size, start, max(expected_size + 0x80, 256, 0x1200))

    def request42(self, addr: int, expected_size: int) -> bytes:
        resp = self.request42_raw(addr, expected_size)
        return normalize_record_response(resp, addr, expected_size)


def _supported_payload_addr(v: int) -> bool:
    return expected_len_for_addr(v) is not None


def _parse_header_flat55(header: bytes, base: int = 0) -> list[int]:
    """Parse live COM 0x55 as PelengPC.exe does.

    Reversed path 0x4249C0 copies the first 16 bytes as header, then copies
    buffer+0x10 into this+0x3C and stores count = (payload_len / 2) - 1.
    Later 0x41C550 reads exactly that many WORD IDs.  Therefore the live 55
    payload is a flat uint16 list, not the PLG/file block stream parsed by
    0x41B008.
    """
    ids: list[int] = []
    stop_found = False
    start = base + 0x10
    if len(header) <= start + 1:
        _parse_header_flat55.stop_found = False  # type: ignore[attr-defined]
        _parse_header_flat55.words_total = 0  # type: ignore[attr-defined]
        _parse_header_flat55.words_used = 0  # type: ignore[attr-defined]
        return ids

    payload_len = len(header) - start
    words_total = payload_len // 2
    # Exact PelengPC: this+0x38 = (actual-16)/2 - 1.  The last WORD is a
    # terminator/guard and is not fed to 0x41C550.
    words_used = max(0, words_total - 1)
    for i in range(words_used):
        off = start + i * 2
        v = header[off] | (header[off + 1] << 8)
        if v in (0xFFFF, 0xFFFD):
            stop_found = True
        if _supported_payload_addr(v):
            ids.append(v)
    _parse_header_flat55.stop_found = stop_found  # type: ignore[attr-defined]
    _parse_header_flat55.words_total = words_total  # type: ignore[attr-defined]
    _parse_header_flat55.words_used = words_used  # type: ignore[attr-defined]
    return ids


def _parse_plg_block_stream(header: bytes, base: int = 0) -> list[int]:
    """Parse PLG/file buffer blocks, not the live 0x55 COM catalogue.

    Reversed function 0x41B008 scans this+0x314 from offset 0x10. Each block
    starts with WORD id and WORD block_len; block_len is validated against the
    expected-length table and the offset advances by block_len. This is useful
    for imported PLG/flash buffers, but must not be selected for live 55.
    """
    ids: list[int] = []
    seen: set[int] = set()
    stop_found = False
    off = base + 0x10
    while off + 3 < len(header):
        v = header[off] | (header[off + 1] << 8)
        if v == 0xFFFF:
            stop_found = True
            break
        if v == 0x0000:
            off += 2
            continue
        block_len = header[off + 2] | (header[off + 3] << 8)
        expected = expected_len_for_addr(v)
        if expected and block_len == expected and off + block_len <= len(header):
            if v not in seen:
                ids.append(v)
                seen.add(v)
            off += block_len
            continue
        break
    _parse_plg_block_stream.stop_found = stop_found  # type: ignore[attr-defined]
    return ids


def _score_header_ids(ids: list[int]) -> int:
    # Prefer realistic catalogues: reports dominate, settings/protocols present,
    # unknowns are already filtered out before scoring.
    settings = sum(1 for x in ids if 1000 <= x <= 1999)
    prot = sum(1 for x in ids if 4000 <= x <= 4999 or 6000 <= x <= 6999)
    reports = sum(1 for x in ids if 10000 <= x <= 29999)
    return len(ids) * 3 + min(settings, 80) + min(prot, 30) + min(reports, 250)


def parse_header_addresses(header: bytes) -> list[int]:
    """Parse live 0x55 catalogue as the original Idx payload.

    Exact live COM path from PelengPC.exe 0x4249C0 + 0x41C550:
      * the first 16 bytes of the 55 answer are service header;
      * payload starts at rx + 0x10;
      * count = ((actual_len - 0x10) // 2) - 1;
      * 0x41C550 copies exactly `count` WORDs from payload into Idx.

    Round42 correction: DO NOT filter, de-duplicate, sort or expand here.
    Round44 correction: live proxy/sniffer/device test confirmed parity E gives stable 218 report Idx (>10000). Default is now 19200 8E1; keep parity selector for A/B tests.
    This function returns the raw Idx WORD stream in the same order as the
    device returned it.  The read plan may later skip IDs for unchecked GUI
    categories or unknown length-table ranges, but the source ordering remains
    original.
    """
    parse_header_addresses.stop_found = False  # type: ignore[attr-defined]
    parse_header_addresses.base = 0x10  # type: ignore[attr-defined]
    parse_header_addresses.recovered = 0  # type: ignore[attr-defined]
    parse_header_addresses.mode = "flat55_idx_order"  # type: ignore[attr-defined]
    parse_header_addresses.words_total = 0  # type: ignore[attr-defined]
    parse_header_addresses.words_used = 0  # type: ignore[attr-defined]
    parse_header_addresses.raw_words = []  # type: ignore[attr-defined]

    if not header or len(header) <= 0x10:
        return []

    payload_len = len(header) - 0x10
    words_total = payload_len // 2
    words_used = max(0, words_total - 1)
    parse_header_addresses.words_total = words_total  # type: ignore[attr-defined]
    parse_header_addresses.words_used = words_used  # type: ignore[attr-defined]

    idx: list[int] = []
    start = 0x10
    for i in range(words_used):
        off = start + i * 2
        v = header[off] | (header[off + 1] << 8)
        # Exact C behavior: only the final WORD is dropped by words_used.
        # Do NOT stop early on FF FF / FD FF-like words; in real report-heavy
        # catalogues this can cut off later 10xxx/13xxx report runs. Keep such
        # words in the raw list as diagnostics/Other if they are not valid IDs.
        if v in (0xFFFF, 0xFFFD):
            parse_header_addresses.stop_found = True  # type: ignore[attr-defined]
        idx.append(v)

    parse_header_addresses.raw_words = idx[:]  # type: ignore[attr-defined]
    return idx

def header_bucket_counts(ids: list[int]) -> dict[str, int]:
    """Bucket 0x55 IDs using the confirmed PelengPC range table.

    Earlier UD2102base notes used broad buckets (0<ID<6000, 6000..10000).
    The PelengPC expected_len table is more precise for this build:
      1000..1999 settings, 4000..4999/6000..6999 protocols,
      5000..5999 B-scan, 10000..29999 reports.
    """
    return {
        "settings": sum(1 for x in ids if 1000 <= x <= 1999),
        "protocols": sum(1 for x in ids if (4000 <= x <= 4999) or (6000 <= x <= 6999)),
        "bscan": sum(1 for x in ids if 5000 <= x <= 5999),
        "reports": sum(1 for x in ids if 10000 <= x <= 29999),
        "unknown": sum(1 for x in ids if expected_len_for_addr(x) is None),
    }


def _is_control_report_addr(addr: int) -> bool:
    """True for SHORTPROT2 control report buckets seen in PelengPC live 55.

    The 55 answer contains many byte patterns that can look like 20xxx/29xxx
    when interpreted on the wrong WORD alignment.  For the "Отчёты контроля"
    tab we only use the stable live clusters 101xx..106xx and late 133xx/134xx.
    Thickness-meter report_v2 ranges remain decodable if explicitly requested
    elsewhere, but they must not pollute the control-report scan plan.
    """
    base = (int(addr) // 100) * 100
    row = int(addr) % 100
    return row >= 1 and row <= 99 and (10100 <= base <= 10600 or base in (13300, 13400))


def recover_report_runs_from_55(header: bytes) -> dict[int, list[tuple[int, int, int]]]:
    """Recover report-id runs from a raw 0x55 answer byte-wise.

    Round40 reverse note:
      The user's direct 55 dump contains clean little-endian report runs such as
      75 27 76 27 ... = 10101,10102,..., but different runs can start on
      different byte parity.  A single flat WORD grid therefore misses some
      report buckets, e.g. 13303/13304 and 13401..13404.  This function does
      not replace the original flat parser for general IDs; it is a targeted
      recovery pass for report scan planning.
    """
    out: dict[int, list[tuple[int, int, int]]] = {}
    n = len(header or b"")
    for off in range(0, max(0, n - 1)):
        addr = header[off] | (header[off + 1] << 8)
        if not _is_control_report_addr(addr):
            continue
        # Skip the middle of an already-detected +1 run.
        if off >= 2:
            prev = header[off - 2] | (header[off - 1] << 8)
            if prev == addr - 1 and _is_control_report_addr(prev):
                continue
        run = [addr]
        pos = off + 2
        cur = addr
        while pos + 1 < n:
            nxt = header[pos] | (header[pos + 1] << 8)
            if nxt == cur + 1 and _is_control_report_addr(nxt):
                run.append(nxt)
                cur = nxt
                pos += 2
                continue
            break
        if len(run) < 2:
            continue
        base = (run[0] // 100) * 100
        # Avoid tiny accidental pairs outside the known report clusters.
        if base not in (10100, 10200, 10300, 10400, 10500, 10600, 13300, 13400):
            continue
        out.setdefault(base, []).append((off, run[0] % 100, run[-1] % 100))
    recover_report_runs_from_55.runs = out  # type: ignore[attr-defined]
    return out


def report_ranges_from_55_runs(header: bytes) -> dict[int, int]:
    """Build original-like report container ranges from byte-wise 55 runs."""
    runs = recover_report_runs_from_55(header)
    ranges: dict[int, int] = {}
    for base, rr in sorted(runs.items()):
        rows: set[int] = set()
        for _off, a, b in rr:
            rows.update(range(a, b + 1))
        if not rows:
            continue
        max_seen = max(rows)
        if base in (10100, 10200, 10400, 10500, 10600):
            # Main containers in original UI are row-based.  A sparse set of
            # anchors like 10201/10202/10213/10214/10225/10226 means "read the
            # bucket", not only those six rows.
            ranges[base] = max(30, max_seen)
        elif base == 10300:
            # The posted 55 has 10302..10339 split into two adjacent runs; scan
            # 10301 as well, because original row numbering is 1-based.
            ranges[base] = max(39, max_seen)
        elif base in (13300, 13400):
            # PLG comparison showed these late containers have four rows.
            ranges[base] = max(4, max_seen)
    report_ranges_from_55_runs.ranges = ranges  # type: ignore[attr-defined]
    return ranges


def device_no_from_header(header: bytes) -> Optional[int]:
    if len(header) >= 2:
        v = safe_le16(header, 0)
        if 0 < v < 65535:
            return v
    return None


class PelengDB:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.bulk_depth = 0
        # Faster bulk insert/update for ordinary UI collection. WAL/NORMAL keeps
        # data reasonably safe but avoids an fsync per 0x42 record.
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA temp_store=MEMORY")
        except Exception:
            pass
        self.init_schema()

    def _commit(self) -> None:
        if getattr(self, "bulk_depth", 0) <= 0:
            self.conn.commit()

    def begin_bulk(self) -> None:
        if self.bulk_depth == 0:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                # Already inside a transaction; continue with deferred commits.
                pass
        self.bulk_depth += 1

    def end_bulk(self) -> None:
        if self.bulk_depth > 0:
            self.bulk_depth -= 1
        if self.bulk_depth == 0:
            self.conn.commit()

    def init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS raw_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                address INTEGER NOT NULL UNIQUE,
                category INTEGER NOT NULL,
                kind TEXT NOT NULL,
                raw BLOB NOT NULL,
                raw_len INTEGER NOT NULL,
                device_no INTEGER,
                header_hex TEXT
            );

            CREATE TABLE IF NOT EXISTS raw_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                address INTEGER NOT NULL,
                category INTEGER NOT NULL,
                kind TEXT NOT NULL,
                raw BLOB NOT NULL,
                raw_len INTEGER NOT NULL,
                device_no INTEGER,
                header_hex TEXT
            );

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_id INTEGER NOT NULL,
                address INTEGER NOT NULL UNIQUE,
                NUMBER TEXT, NUMKOD TEXT, DATEFORM TEXT, TIMEFORM TEXT,
                KODOPERA TEXT, NAMEOPERA TEXT, NUMVERS TEXT, NUMPRIB TEXT,
                TYPEVAR TEXT, NUMOBJ TEXT, CODEDEF TEXT, PROTOCOL TEXT, NUMZAP TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS protocols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_id INTEGER NOT NULL,
                address INTEGER NOT NULL UNIQUE,
                NUMBER TEXT, NUMKOD TEXT, TYPEZAP TEXT, DATEFORM TEXT, TIMEFORM TEXT,
                KODOPERA TEXT, NAMEOPERA TEXT, NUMVERS TEXT, NUMPRIB TEXT,
                TYPEVAR TEXT, NUMOBJ TEXT, SMELTING TEXT, INDMAKER TEXT, MAKETIME TEXT,
                DEFEKT TEXT, CODEDEF TEXT, SETTING_NO TEXT, SETTING_ADDR TEXT,
                GRAPH_ADDR TEXT, SPECIAL TEXT, NUMZAP TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_id INTEGER NOT NULL,
                address INTEGER NOT NULL UNIQUE,
                NUMBER TEXT, NUMKOD TEXT, TYPEZAP TEXT, DATEFORM TEXT, TIMEFORM TEXT,
                KODOPERA TEXT, NAMEOPERA TEXT, NUMVERS TEXT, NUMPRIB TEXT,
                SETTING_NO TEXT, TYPEVAR TEXT, NUMZAP TEXT,
                params_json TEXT,
                created_at TEXT NOT NULL
            );


            CREATE TABLE IF NOT EXISTS protocol_diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address INTEGER NOT NULL UNIQUE,
                linked_graph_addr INTEGER,
                setting_addr INTEGER,
                fw_code TEXT,
                record_len INTEGER,
                graph_found INTEGER,
                graph_len INTEGER,
                setting_found INTEGER,
                setting_no INTEGER,
                zones_match_setting INTEGER,
                special_geometry INTEGER,
                warnings_json TEXT,
                created_at TEXT NOT NULL
            );
        """)
        self._migrate_schema()
        self._commit()

    def _migrate_schema(self) -> None:
        migrations = {
            "reports": {"SMELTING": "SMELTING TEXT"},
        }
        for table, cols in migrations.items():
            existing = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
            for col, ddl in cols.items():
                if col not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    @staticmethod
    def now() -> str:
        return dt.datetime.now().isoformat(timespec="seconds")

    def save_raw(self, addr: int, kind: str, raw: bytes, device_no: Optional[int], header: bytes = b"", event_raw: Optional[bytes] = None) -> int:
        created = self.now()
        # Append-only trace first: raw_events must be the exact wire response.
        # raw_records remains the normalized/latest record used by decoders.
        # Earlier builds stored only normalized bytes, which made RAW ZIP useless
        # for reverse when a delayed prefix/tail was stripped by normalize_record_response().
        eraw = raw if event_raw is None else event_raw
        self.conn.execute(
            """
            INSERT INTO raw_events(created_at,address,category,kind,raw,raw_len,device_no,header_hex)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (created, addr, category_of_addr(addr), kind, eraw, len(eraw), device_no, header.hex()),
        )
        # raw_records is the visible/latest table.  Do not let a later empty
        # timeout hide a useful 85-byte diagnostic frame, and do not let an
        # incomplete frame replace a complete one.  raw_events above still keeps
        # every request exactly as it happened.
        existing = self.conn.execute("SELECT raw_len, kind FROM raw_records WHERE address=?", (addr,)).fetchone()
        should_upsert_latest = True
        if existing is not None:
            old_len = int(existing["raw_len"] or 0)
            new_len = len(raw)
            old_kind = str(existing["kind"] or "")
            if new_len == 0 and old_len > 0:
                should_upsert_latest = False
            elif "incomplete" in kind and old_len > new_len:
                should_upsert_latest = False
            elif "incomplete" in kind and old_kind not in ("", kind) and old_len >= new_len:
                should_upsert_latest = False
        if should_upsert_latest:
            self.conn.execute(
                """
                INSERT INTO raw_records(created_at,address,category,kind,raw,raw_len,device_no,header_hex)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(address) DO UPDATE SET
                    created_at=excluded.created_at,
                    category=excluded.category,
                    kind=excluded.kind,
                    raw=excluded.raw,
                    raw_len=excluded.raw_len,
                    device_no=excluded.device_no,
                    header_hex=excluded.header_hex
                """,
                (created, addr, category_of_addr(addr), kind, raw, len(raw), device_no, header.hex()),
            )
        self._commit()
        row = self.conn.execute("SELECT id FROM raw_records WHERE address=?", (addr,)).fetchone()
        return int(row["id"])

    def get_raw_by_addr(self, addr: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM raw_records WHERE address=?", (addr,)).fetchone()

    def save_report(self, raw_id: int, addr: int, fields: dict[str, str]) -> None:
        created = self.now()
        cols = ["raw_id", "address"] + REPORT_COLS + ["created_at"]
        vals = [raw_id, addr] + [fields.get(c, "") for c in REPORT_COLS] + [created]
        placeholders = ",".join("?" for _ in vals)
        update = ",".join(f"{c}=excluded.{c}" for c in REPORT_COLS + ["raw_id", "created_at"])
        self.conn.execute(
            f"INSERT INTO reports({','.join(cols)}) VALUES({placeholders}) ON CONFLICT(address) DO UPDATE SET {update}",
            vals,
        )
        self._commit()

    def save_protocol(self, raw_id: int, addr: int, fields: dict[str, str]) -> None:
        created = self.now()
        cols = ["raw_id", "address"] + PROTOCOL_COLS + ["created_at"]
        vals = [raw_id, addr] + [fields.get(c, "") for c in PROTOCOL_COLS] + [created]
        placeholders = ",".join("?" for _ in vals)
        update = ",".join(f"{c}=excluded.{c}" for c in PROTOCOL_COLS + ["raw_id", "created_at"])
        self.conn.execute(
            f"INSERT INTO protocols({','.join(cols)}) VALUES({placeholders}) ON CONFLICT(address) DO UPDATE SET {update}",
            vals,
        )
        self._commit()

    def save_setting(self, raw_id: int, addr: int, fields: dict[str, str], params: dict[str, Any]) -> None:
        created = self.now()
        cols = ["raw_id", "address"] + SETTING_COLS + ["params_json", "created_at"]
        vals = [raw_id, addr] + [fields.get(c, "") for c in SETTING_COLS] + [json.dumps(params, ensure_ascii=False)] + [created]
        placeholders = ",".join("?" for _ in vals)
        update = ",".join(f"{c}=excluded.{c}" for c in SETTING_COLS + ["raw_id", "params_json", "created_at"])
        self.conn.execute(
            f"INSERT INTO settings({','.join(cols)}) VALUES({placeholders}) ON CONFLICT(address) DO UPDATE SET {update}",
            vals,
        )
        self._commit()


    def save_protocol_diagnostic(self, diag: dict[str, Any]) -> None:
        created = self.now()
        self.conn.execute(
            """
            INSERT INTO protocol_diagnostics(
                address, linked_graph_addr, setting_addr, fw_code, record_len,
                graph_found, graph_len, setting_found, setting_no, zones_match_setting,
                special_geometry, warnings_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(address) DO UPDATE SET
                linked_graph_addr=excluded.linked_graph_addr,
                setting_addr=excluded.setting_addr,
                fw_code=excluded.fw_code,
                record_len=excluded.record_len,
                graph_found=excluded.graph_found,
                graph_len=excluded.graph_len,
                setting_found=excluded.setting_found,
                setting_no=excluded.setting_no,
                zones_match_setting=excluded.zones_match_setting,
                special_geometry=excluded.special_geometry,
                warnings_json=excluded.warnings_json,
                created_at=excluded.created_at
            """,
            (
                diag.get("address"), diag.get("linked_graph_addr"), diag.get("setting_addr"),
                diag.get("fw_code"), diag.get("record_len"), diag.get("graph_found"),
                diag.get("graph_len"), diag.get("setting_found"), diag.get("setting_no"),
                diag.get("zones_match_setting"), diag.get("special_geometry"),
                diag.get("warnings_json", "[]"), created,
            ),
        )
        self._commit()

    def diagnostic_by_addr(self, addr: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM protocol_diagnostics WHERE address=?", (addr,)).fetchone()

    def rows(self, table: str) -> list[sqlite3.Row]:
        return list(self.conn.execute(f"SELECT * FROM {table} ORDER BY address"))

    def row_by_id(self, table: str, row_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()

    def row_by_addr(self, table: str, addr: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(f"SELECT * FROM {table} WHERE address=?", (addr,)).fetchone()

    def clear_all(self) -> None:
        self.conn.executescript("DELETE FROM reports; DELETE FROM protocols; DELETE FROM settings; DELETE FROM protocol_diagnostics; DELETE FROM raw_records; DELETE FROM raw_events;")
        self._commit()

    def export_raw_zip(self, zip_path: str) -> int:
        """Сохраняет RAW текущей сессии в ZIP: manifest.csv + raw/*.bin + raw_events/*.bin."""
        rows = self.rows("raw_records")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest_lines = [
                "id,address,category,kind,raw_len,device_no,created_at,filename,header_hex\n"
            ]
            for row in rows:
                raw = bytes(row["raw"])
                fname = f"raw/{int(row['address']):05d}_{row['kind']}_{int(row['raw_len']):04X}.bin"
                zf.writestr(fname, raw)
                manifest_lines.append(
                    f"{row['id']},{row['address']},{row['category']},{row['kind']},{row['raw_len']},{row['device_no'] or ''},{row['created_at']},{fname},{row['header_hex'] or ''}\n"
                )
            zf.writestr("manifest.csv", "".join(manifest_lines).encode("utf-8-sig"))

            # Append-only event trace: useful when a later read overwrites the
            # per-address raw_records row, or when an incomplete 0x55 frame must
            # be inspected exactly as it arrived.
            try:
                event_rows = list(self.conn.execute("SELECT * FROM raw_events ORDER BY id"))
            except Exception:
                event_rows = []
            event_manifest = [
                "event_id,address,category,kind,raw_len,device_no,created_at,filename,header_hex\n"
            ]
            for erow in event_rows:
                eraw = bytes(erow["raw"])
                efname = f"raw_events/{int(erow['id']):06d}_{int(erow['address']):05d}_{erow['kind']}_{int(erow['raw_len']):04X}.bin"
                zf.writestr(efname, eraw)
                event_manifest.append(
                    f"{erow['id']},{erow['address']},{erow['category']},{erow['kind']},{erow['raw_len']},{erow['device_no'] or ''},{erow['created_at']},{efname},{erow['header_hex'] or ''}\n"
                )
            zf.writestr("raw_events_manifest.csv", "".join(event_manifest).encode("utf-8-sig"))

            # Дополнительно кладём короткую справку, чтобы архив можно было открыть отдельно от GUI.
            zf.writestr(
                "README.txt",
                (
                    "Peleng VAGON 6.43 RAW export\n"
                    "raw/ contains latest normalized payload per address.\n"
                    "raw_events/ contains append-only 0x42 trace, including incomplete frames.\n"
                    "manifest.csv contains id,address,category,kind,raw_len,device_no,created_at,filename.\n"
                ).encode("utf-8")
            )
        return len(rows)


class DetailWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str):
        super().__init__(master)
        self.title(title)
        self.geometry("1100x760")
        self.minsize(900, 580)

    def save_raw_file(self, raw: bytes, default_name: str) -> None:
        path = filedialog.asksaveasfilename(
            title="Сохранить RAW",
            initialfile=default_name,
            defaultextension=".bin",
            filetypes=[("RAW binary", "*.bin"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "wb") as f:
            f.write(raw)
        messagebox.showinfo("RAW сохранён", f"Сохранено: {path}")

    def add_kv_tree(self, parent: tk.Widget, rows: list[tuple[str, Any]], height: int = 20) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=("field", "value"), show="headings", height=height)
        tree.heading("field", text="Поле")
        tree.heading("value", text="Значение")
        tree.column("field", width=260, stretch=False)
        tree.column("value", width=650, stretch=True)
        for k, v in rows:
            tree.insert("", tk.END, values=(FIELD_LABELS.get(str(k), str(k)), "" if v is None else str(v)))
        tree.pack(fill=tk.BOTH, expand=True)
        return tree


class SettingDetail(DetailWindow):
    def __init__(self, master: tk.Misc, row: sqlite3.Row, raw: bytes):
        super().__init__(master, f"Настройка {row['address']}")
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        f1 = ttk.Frame(nb, padding=8)
        nb.add(f1, text="Дешифровка")
        rows = [(c, row[c]) for c in SETTING_COLS if c in row.keys()]
        try:
            params = json.loads(row["params_json"] or "{}")
        except Exception:
            params = decode_nastr2_params_643(raw, int(row["address"]))
        rows.extend(sorted(params.items()))
        self.add_kv_tree(f1, rows)
        f2 = ttk.Frame(nb, padding=8)
        nb.add(f2, text="Raw hex")
        ttk.Button(f2, text="Сохранить RAW...", command=lambda: self.save_raw_file(raw, f"setting_{row['address']}.bin")).pack(anchor="e", pady=(0, 6))
        txt = tk.Text(f2, wrap=tk.NONE)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", hexdump_preview(raw, 4096))
        txt.configure(state=tk.DISABLED)


class ReportDetail(DetailWindow):
    def __init__(self, master: tk.Misc, row: sqlite3.Row, raw: bytes):
        super().__init__(master, f"Отчёт {row['address']}")
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        f1 = ttk.Frame(nb, padding=8)
        nb.add(f1, text="Поля")
        self.add_kv_tree(f1, [(c, row[c]) for c in REPORT_COLS if c in row.keys()])
        f2 = ttk.Frame(nb, padding=8)
        nb.add(f2, text="Raw hex")
        ttk.Button(f2, text="Сохранить RAW...", command=lambda: self.save_raw_file(raw, f"report_{row['address']}.bin")).pack(anchor="e", pady=(0, 6))
        txt = tk.Text(f2, wrap=tk.NONE)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", hexdump_preview(raw, 1024))
        txt.configure(state=tk.DISABLED)


class RawDetail(DetailWindow):
    def __init__(self, master: tk.Misc, row: sqlite3.Row):
        super().__init__(master, f"Raw {row['address']} / {row['kind']}")
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        f1 = ttk.Frame(nb, padding=8)
        nb.add(f1, text="Метаданные")
        rows = [(k, row[k]) for k in row.keys() if k != "raw"]
        self.add_kv_tree(f1, rows)
        f2 = ttk.Frame(nb, padding=8)
        nb.add(f2, text="Raw hex")
        txt = tk.Text(f2, wrap=tk.NONE)
        txt.pack(fill=tk.BOTH, expand=True)
        raw = bytes(row["raw"])
        txt.insert("1.0", f"address={row['address']} kind={row['kind']} len={len(raw)}\n\n")
        txt.insert(tk.END, hexdump_preview(raw, 8192))
        txt.configure(state=tk.DISABLED)


class ProtocolDetail(DetailWindow):
    def __init__(self, master: tk.Misc, db: PelengDB, row: sqlite3.Row):
        super().__init__(master, f"Протокол А-развёртки {row['address']}")
        self.db = db
        self.row = row
        self.protocol_raw = self._raw_for(int(row["address"])) or b""
        graph_addr = int(row["GRAPH_ADDR"] or graph_addr_for_protocol(int(row["address"])))
        self.graph_addr = graph_addr
        self.graph_raw = self._raw_for(graph_addr) or self.protocol_raw
        setting_addr = int(row["SETTING_ADDR"] or 0) if str(row["SETTING_ADDR"] or "").isdigit() else 0
        self.setting_raw = self._raw_for(setting_addr) if setting_addr else None
        self.graph: dict[str, Any] = {}
        self.zones: dict[str, Any] = {}
        self.diag_row = self.db.diagnostic_by_addr(int(row["address"]))
        try:
            self.graph = decode_ascan_graph_643(self.graph_raw)
        except Exception as exc:
            self.graph = {"error": str(exc)}
        try:
            self.zones = decode_ascan_zones_643(self.graph_raw)
        except Exception as exc:
            self.zones = {"error": str(exc)}
        self._build()

    def _raw_for(self, addr: int) -> Optional[bytes]:
        r = self.db.get_raw_by_addr(addr)
        return bytes(r["raw"]) if r else None

    def _build(self) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=2)
        paned.add(right, weight=3)

        nb = ttk.Notebook(left)
        nb.pack(fill=tk.BOTH, expand=True)
        f_protocol = ttk.Frame(nb, padding=8)
        nb.add(f_protocol, text="Поля протокола")
        rows = [(c, self.row[c]) for c in PROTOCOL_COLS if c in self.row.keys()]
        try:
            tcode_s = str(self.row["TYPEVAR"] or "").split(" ", 1)[0]
            tcode = int(tcode_s) if tcode_s.isdigit() else detect_typevar_code(self.protocol_raw, setting_no=protocol_setting_no_643(self.protocol_raw))
            info = typevar_info_643(tcode)
            rows.extend([("object", info.get("object", "")), ("detail", info.get("detail", "")), ("ntd", info.get("ntd", ""))])
        except Exception:
            pass
        try:
            spd = safe_le16(self.protocol_raw, 0x77, 5900)
            defect = decode_defect_643(self.protocol_raw, spd, 0.0)
            rows.extend([
                ("defect_m", defect.get("defect_m", "")),
                ("defect_y", f"{float(defect.get('defect_y', 0)):.1f}"),
                ("defect_x", f"{float(defect.get('defect_x', 0)):.1f}"),
                ("defect_r", f"{float(defect.get('defect_r', 0)):.1f}"),
                ("defect_t", f"{float(defect.get('defect_t', 0)):.1f}"),
                ("detectability_db", defect.get("detectability_db", "")),
                ("CODEDEF", defect.get("defect_code_text", "") or defect.get("defect_code_numeric", "")),
            ])
        except Exception:
            pass
        rows.extend((f"graph.{k}", v) for k, v in self.graph.items() if k not in {"raw_block", "samples", "amplitudes"})
        rows.extend((f"zone.{k}", v) for k, v in self.zones.items())
        if self.diag_row:
            for k in ("fw_code", "record_len", "linked_graph_addr", "graph_found", "graph_len", "setting_addr", "setting_found", "zones_match_setting", "special_geometry", "warnings_json"):
                rows.append((f"diag.{k}", self.diag_row[k]))
        self.add_kv_tree(f_protocol, rows, height=24)

        f_setting = ttk.Frame(nb, padding=8)
        nb.add(f_setting, text="Настройка")
        if self.setting_raw:
            try:
                params = decode_nastr2_params_643(self.setting_raw, int(self.row["SETTING_ADDR"] or 0))
                srows = sorted(params.items())
            except Exception as exc:
                srows = [("error", str(exc))]
        else:
            srows = [("warning", "Связанная настройка не загружена в БД")]
        self.add_kv_tree(f_setting, srows, height=24)

        f_raw = ttk.Frame(nb, padding=8)
        nb.add(f_raw, text="Raw")
        btns = ttk.Frame(f_raw)
        btns.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(btns, text="Сохранить RAW протокола...", command=lambda: self.save_raw_file(self.protocol_raw, f"protocol_{self.row['address']}.bin")).pack(side=tk.LEFT)
        ttk.Button(btns, text="Сохранить RAW графика...", command=lambda: self.save_raw_file(self.graph_raw, f"graph_{self.graph_addr}.bin")).pack(side=tk.LEFT, padx=(8,0))
        txt = tk.Text(f_raw, wrap=tk.NONE)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", f"Protocol raw addr {self.row['address']} len={len(self.protocol_raw)}\n")
        txt.insert(tk.END, hexdump_preview(self.protocol_raw, 2048))
        txt.insert(tk.END, f"\n\nGraph raw addr {self.graph_addr} len={len(self.graph_raw)}\n")
        txt.insert(tk.END, hexdump_preview(self.graph_raw, 4096))
        txt.configure(state=tk.DISABLED)

        ttk.Label(right, text="A-развёртка 6.42/6.43: график = хвостовые 0xF4 байта, baseline=0x8C", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.canvas = tk.Canvas(right, bg="white", height=520)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(6, 6))
        self.canvas.bind("<Configure>", lambda _e: self.draw_graph())
        ttk.Button(right, text="Перерисовать", command=self.draw_graph).pack(anchor="e")
        self.after(150, self.draw_graph)

    def draw_graph(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 300), max(c.winfo_height(), 220)
        ml, mr, mt, mb = 48, 24, 24, 38
        pw, ph = w - ml - mr, h - mt - mb
        c.create_rectangle(ml, mt, w - mr, h - mb, outline="#888")
        if "samples" not in self.graph:
            c.create_text(w // 2, h // 2, text=self.graph.get("error", "Нет графика"), fill="#555")
            return
        samples = self.graph["samples"]
        n = len(samples)
        if n == 0:
            c.create_text(w // 2, h // 2, text="Пустой график", fill="#555")
            return

        duration_t10 = int(self.zones.get("duration_t10", 7920) or 7920)

        def x_by_raw(raw_x: int) -> float:
            return ml + (raw_x / max(1, duration_t10)) * pw

        def x_of_i(i: int) -> float:
            return ml + (i / max(1, GRAPH_DRAW_COUNT - 1)) * pw

        def y_of_sample(s: int) -> float:
            # Рисуем как оригинальный baseline: sample=0x8C на базовой линии.
            amp = s - GRAPH_BASELINE
            # ±140 амплитуды примерно на высоту графика.
            return mt + ph * 0.5 - (amp / 140.0) * (ph * 0.5)

        # baseline
        y0 = y_of_sample(GRAPH_BASELINE)
        c.create_line(ml, y0, w - mr, y0, fill="#999", dash=(3, 3))
        c.create_text(8, y0, text="0 / 0x8C", anchor="w", fill="#666")

        # zones
        if "error" not in self.zones:
            for label, pfx, fill, stipple in (("ВС1", "vs1", "#b7d7ff", "gray25"), ("ВС2", "vs2", "#ffd4b7", "gray25")):
                x1_raw = int(self.zones.get(f"{pfx}_start_raw", 0) or 0)
                x2_raw = int(self.zones.get(f"{pfx}_end_raw", 0) or 0)
                if x2_raw < x1_raw:
                    x1_raw, x2_raw = x2_raw, x1_raw
                x1, x2 = x_by_raw(x1_raw), x_by_raw(x2_raw)
                if x2 > x1:
                    c.create_rectangle(x1, mt, x2, h - mb, fill=fill, stipple=stipple, outline="")
                    c.create_line(x1, mt, x1, h - mb, fill="#333", dash=(2, 2))
                    c.create_line(x2, mt, x2, h - mb, fill="#333", dash=(2, 2))
                    method = self.zones.get(f"{pfx}_method", "")
                    thr = self.zones.get(f"{pfx}_threshold", "")
                    c.create_text((x1 + x2) / 2, mt + 12, text=f"{label} {method} {thr}% [{x1_raw}..{x2_raw}]", fill="#333")

            # extra interval / VRCH marker
            ex1 = int(self.zones.get("extra_start_raw", 0) or 0)
            ex2 = int(self.zones.get("extra_end_raw", 0) or 0)
            if ex2 < ex1:
                ex1, ex2 = ex2, ex1
            if ex2 > ex1:
                x1, x2 = x_by_raw(ex1), x_by_raw(ex2)
                c.create_rectangle(x1, mt, x2, h - mb, fill="#e5e5e5", stipple="gray12", outline="")
                c.create_text((x1 + x2) / 2, h - mb - 12, text="доп./ВРЧ", fill="#555")

        # grid
        for frac in (0.25, 0.5, 0.75):
            y = mt + ph * frac
            c.create_line(ml, y, w - mr, y, fill="#eee")
        for frac in (0.25, 0.5, 0.75):
            x = ml + pw * frac
            c.create_line(x, mt, x, h - mb, fill="#eee")

        pts: list[float] = []
        for i, s in enumerate(samples):
            pts.extend([x_of_i(i), y_of_sample(s)])
        if len(pts) >= 4:
            c.create_line(*pts, fill="#111", width=1)
        c.create_text(ml, h - 18, anchor="w", fill="#333", text=(
            f"graph_addr={self.graph_addr}, samples={n}, off=0x{self.graph.get('offset', 0):X}, "
            f"min={self.graph.get('min_sample')}, max={self.graph.get('max_sample')}, "
            f"line={'да' if self.graph.get('line_mode') else 'нет'}, special={'да' if self.graph.get('special_geometry') else 'нет'}"
        ))


# ---------------------------------------------------------------------------
# Native-like protocol A-scan sheet (double click), v7.
# This is intentionally presentation-only: it does not modify decoding tables,
# basket logic, transport timings, PostgreSQL export, or stored rows.
# ---------------------------------------------------------------------------

class NativeAscanProtocolSheet(tk.Toplevel):
    """Native PelengPC-like protocol sheet for A-развёртка.

    v8: presentation-only pass.  The layout is fixed-coordinate and follows the
    original PelengPC protocol sheet: every label has its value directly opposite
    it, the A-scan graph is placed under "Развертка:" on the left, defect metrics
    are placed to the right of the graph, then the operator conclusion, settings
    block, additional information and signature.
    """

    PAGE_W = 980
    PAGE_H = 1320

    def __init__(self, master: tk.Misc, db: PelengDB, addr: int):
        super().__init__(master)
        self.db = db
        self.addr = int(addr)
        self.title("Протокол А-развертки")
        self.geometry("1120x900")
        self.minsize(980, 720)
        self.row = db.row_by_addr("protocols", self.addr)
        if not self.row:
            messagebox.showinfo("Протокол", "Протокол ещё не получен/не дешифрован.")
            self.destroy()
            return

        self.protocol_raw = self._raw_for(self.addr) or b""
        try:
            self.graph_addr = int(self.row["GRAPH_ADDR"] or graph_addr_for_protocol(self.addr))
        except Exception:
            self.graph_addr = graph_addr_for_protocol(self.addr)
        self.graph_raw = self._raw_for(self.graph_addr) or self.protocol_raw
        try:
            self.setting_no = int(str(self.row["SETTING_NO"] or "0"))
        except Exception:
            self.setting_no = 0
        try:
            self.setting_addr = int(str(self.row["SETTING_ADDR"] or "0"))
        except Exception:
            self.setting_addr = 1000 + self.setting_no if self.setting_no else 0
        self.setting_raw = self._raw_for(self.setting_addr) if self.setting_addr else None
        self.setting_params = self._decode_setting_params()
        self.graph = self._decode_graph()
        self.zones = self._decode_zones()
        self.defect = self._decode_defect()
        self._build()

    def _raw_for(self, addr: int) -> Optional[bytes]:
        r = self.db.get_raw_by_addr(int(addr))
        return bytes(r["raw"]) if r else None

    def _decode_setting_params(self) -> dict[str, Any]:
        if self.setting_raw:
            try:
                return decode_nastr2_params_643(self.setting_raw, self.setting_addr)
            except Exception as exc:
                return {"error": str(exc)}
        return {}

    def _decode_graph(self) -> dict[str, Any]:
        """Choose the real graph source without changing stored data.

        Native PelengPC draws the A-scan from the record that actually contains
        the 0xF4 sample block.  In live data this can be the selected 4000 record
        itself; a linked 6000 record may be absent or may contain only a short
        0x56 diagnostic/summary frame.  Therefore try both sources and choose the
        graph with the best sample score instead of blindly preferring GRAPH_ADDR.
        """
        best: Optional[dict[str, Any]] = None
        best_score = -10**9
        self.graph_source_raw = b""
        seen: set[bytes] = set()
        for label, raw in (("protocol", self.protocol_raw), ("linked", self.graph_raw)):
            if not raw or raw in seen:
                continue
            seen.add(raw)
            try:
                g = decode_ascan_graph_643(raw)
                samples = bytes(g.get("samples") or [])
                score = _score_graph_block(samples)
                # Prefer a graph with visible variation; still keep the best so
                # the page can show a flat trace if the original data is flat.
                if score > best_score:
                    best_score = score
                    best = dict(g)
                    best["source"] = label
                    self.graph_source_raw = raw
            except Exception:
                continue
        if best is not None:
            return best
        self.graph_source_raw = self.graph_raw or self.protocol_raw
        return {"error": "Нет полного блока графика 0xF4: перечитайте протокол/связанную запись"}

    def _decode_zones(self) -> dict[str, Any]:
        try:
            return decode_ascan_zones_643(getattr(self, "graph_source_raw", None) or self.graph_raw or self.protocol_raw)
        except Exception as exc:
            return {"error": str(exc)}

    def _decode_defect(self) -> dict[str, Any]:
        try:
            speed = int(self.setting_params.get("sound_speed") or safe_le16(self.protocol_raw, 0x77, 5900) or 5900)
            angle = float(self.setting_params.get("angle_deg") or 0)
            return decode_defect_643(self.protocol_raw, speed, angle)
        except Exception:
            return {}

    def _row_get(self, key: str, default: str = "") -> str:
        try:
            v = self.row[key]
            return default if v is None else str(v)
        except Exception:
            return default

    def _typevar_code(self) -> int:
        s = self._row_get("TYPEVAR")
        head = s.split(" ", 1)[0].strip()
        if head.isdigit():
            return int(head)
        try:
            return int(self.setting_params.get("typevar_code") or 0)
        except Exception:
            return 0

    def _typevar_info(self) -> dict[str, str]:
        code = self._typevar_code()
        if code:
            return typevar_info_643(code)
        return {"object": "", "detail": "", "ntd": ""}

    def _header_device_version(self) -> tuple[str, str]:
        dev = self._row_get("NUMPRIB")
        ver = self._row_get("NUMVERS")
        try:
            h = _report_header_for_addr(self.db, self.addr)
            hv = _native_header_version(h) if h else ""
            hd = _native_header_device(h) if h else ""
            if hv:
                ver = hv
            if hd:
                dev = hd
        except Exception:
            pass
        return dev, ver

    @staticmethod
    def _fmt1(v: Any) -> str:
        try:
            return f"{float(v):.1f}"
        except Exception:
            return str(v or "0.0")

    @staticmethod
    def _not_empty(*vals: Any) -> str:
        for v in vals:
            if v is None:
                continue
            s = str(v).strip()
            if s and s.lower() not in ("none", "nan"):
                return s
        return ""

    def _side_value(self) -> str:
        p = self.setting_params or {}
        val = self._not_empty(p.get("side"))
        if val:
            return val
        # Native protocol sheet uses the protocol/detail byte when available.
        b = None
        for off in (0x40, 0x50, 0x60):
            if len(self.protocol_raw) > off and self.protocol_raw[off] in (0, 1, 2, 3):
                b = self.protocol_raw[off]
                break
        return {0: "лев", 1: "прав", 2: "обе", 3: "обе"}.get(b, "")

    def _neck_value(self) -> str:
        p = self.setting_params or {}
        val = self._not_empty(p.get("neck"))
        if val:
            return val
        info_obj = (self._typevar_info().get("object", "") or "").lower()
        # Do not print axle neck text for wheels; native leaves wheel-only/axis-only
        # fields blank depending on TYPEVAR.
        if "колес" in info_obj and "ось" not in info_obj:
            return ""
        if len(self.protocol_raw) > 0x41:
            return {0: "с кольцами", 1: "без колец", 2: "с буксой", 3: "с буксой"}.get(self.protocol_raw[0x41], "")
        return ""

    def _factory_value(self) -> str:
        vals = [self._row_get("INDMAKER"), self.setting_params.get("factory") if self.setting_params else ""]
        for off in (0x3C, 0x4C, 0x2F):
            v = safe_le16(self.protocol_raw, off, 0)
            if 0 < v < 10000:
                vals.append(str(v))
        return self._not_empty(*vals)

    def _year_value(self) -> str:
        vals = [self._row_get("MAKETIME"), self.setting_params.get("production_year") if self.setting_params else ""]
        for off in (0x3E, 0x4E, 0x30):
            v = safe_le16(self.protocol_raw, off, 0)
            if 1900 <= v <= 2099:
                vals.append(str(v))
            elif 0 < v <= 99:
                vals.append(f"20{v:02d}")
        return self._not_empty(*vals)

    def _object_number_value(self) -> str:
        return self._not_empty(self._row_get("NUMOBJ"), best_reverse_digit_field(self.protocol_raw, ((0x10, 0x0B), (0x11, 0x0B), (0x20, 0x0C), (0x21, 0x0C)), 12))

    def _smelting_value(self) -> str:
        return self._not_empty(self._row_get("SMELTING"), best_reverse_digit_field(self.protocol_raw, ((0x33, 0x07), (0x34, 0x07), (0x35, 0x07), (0x45, 0x07)), 8), "0")

    def _build(self) -> None:
        top = tk.Frame(self, bg="#efefef", bd=1, relief=tk.GROOVE)
        top.pack(fill=tk.X)
        for txt, cmd in (("Печать", None), ("Сохранить", None), ("Настройка", None)):
            tk.Button(top, text=txt, width=12, command=cmd or (lambda: None)).pack(side=tk.LEFT, padx=4, pady=6)

        outer = tk.Canvas(self, bg="#333333", highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=outer.yview)
        outer.configure(yscrollcommand=vsb.set)
        outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        page = tk.Canvas(outer, bg="white", width=self.PAGE_W, height=self.PAGE_H, bd=1, relief=tk.SOLID, highlightthickness=0)
        win = outer.create_window(28, 20, anchor="nw", window=page)
        page.bind("<Configure>", lambda e: outer.configure(scrollregion=outer.bbox("all")))
        outer.bind("<Configure>", lambda e: outer.itemconfigure(win, width=min(self.PAGE_W, max(self.PAGE_W, e.width - 70))))
        self.page_canvas = page
        self.graph_canvas = tk.Canvas(page, width=360, height=230, bg="white", bd=0, highlightthickness=0)

        self._draw_page(page)
        self.after(120, self._draw_native_graph)

    def _t(self, x: int, y: int, text: Any, *, size: int = 9, bold: bool = False, anchor: str = "nw", width: Optional[int] = None, spacing1: int = 0) -> int:
        font = ("Arial", size, "bold" if bold else "normal")
        opts: dict[str, Any] = {"text": str(text or ""), "fill": "#111", "font": font, "anchor": anchor}
        if width:
            opts["width"] = width
        if spacing1:
            opts["spacing1"] = spacing1
        return self.page_canvas.create_text(x, y, **opts)

    def _field(self, y: int, label: str, value: Any, *, x_label: int = 62, x_val: int = 220, bold: bool = True) -> None:
        self._t(x_label, y, label, size=9)
        self._t(x_val, y, value, size=11 if bold else 9, bold=bold)
        # Native visual separator line near value column.
        self.page_canvas.create_line(x_val - 8, y - 2, x_val - 8, y + 16, fill="#777")

    def _draw_page(self, c: tk.Canvas) -> None:
        info = self._typevar_info()
        dev, ver = self._header_device_version()
        date = self._row_get("DATEFORM")
        time_s = self._row_get("TIMEFORM")
        num = self._row_get("NUMKOD") or str(self.addr % 1000)
        operator_code = self._row_get("KODOPERA") or "00"
        operator_name = _operator_name_for_code(operator_code, self._row_get("NAMEOPERA"))
        object_name = info.get("object", "") or _short_typevar(self._row_get("TYPEVAR"))
        detail = info.get("detail", "")
        ntd = info.get("ntd", "")
        smelting = self._row_get("SMELTING")
        refl = str(self.defect.get("reflector_no", "0") or "0")

        # Header block, matching native coordinates.
        self._t(62, 38, "П Р О Т О К О Л  №", size=12, bold=True)
        self._t(250, 38, num, size=12, bold=True)
        self._t(62, 62, "ультразвукового контроля, проведенного", size=9)
        self._t(62, 84, f"дефектоскопом УД2-102 № {dev}, {date} {time_s}, Версия {ver}", size=9)

        y = 132
        dy = 22
        self._field(y + dy*0, "Предприятие", _report_enterprise())
        self._field(y + dy*1, "Подразделение", _report_subdivision())
        self._field(y + dy*2, "Оператор: шифр", operator_code, bold=False)
        self._field(y + dy*3, "Фамилия", operator_name)
        self._field(y + dy*4, "Объект", object_name)
        self._field(y + dy*5, "Номер объекта", self._object_number_value(), bold=False)
        self._field(y + dy*6, "Деталь", detail)
        self._field(y + dy*7, "НТД на контроль", ntd)
        self._field(y + dy*8, "Сторона", self._side_value())
        self._field(y + dy*9, "Плавка", self._smelting_value(), bold=False)
        self._field(y + dy*10, "Год изготовления", self._year_value(), bold=False)
        self._field(y + dy*11, "Завод-изготовитель", self._factory_value(), bold=False)
        self._field(y + dy*12, "шейка", self._neck_value(), bold=False)
        self._field(y + dy*13, "№ отражателя", refl, bold=False)

        # A-scan graph and defect metrics.
        self._t(62, 438, "Развертка :", size=9)
        c.create_window(62, 462, anchor="nw", window=self.graph_canvas)
        self._draw_metric_block(472, 500)

        # Operator conclusion.
        self._t(62, 730, "З А К Л Ю Ч Е Н И Е  О П Е Р А Т О Р А :", size=10, bold=True)
        c.create_rectangle(62, 756, 910, 830, outline="#333")
        present = bool(self.defect.get("defect_present")) or (self._row_get("DEFEKT").lower() == "есть")
        concl = "Признак дефекта присутствует" if present else "Признак дефекта отсутствует"
        self._t(70, 764, concl, size=11, bold=True)

        # Settings block.
        self._draw_settings_block(62, 850)

        # Additional information and signature.
        self._t(62, 1218, "Дополнительная информация", size=10, bold=True)
        c.create_rectangle(62, 1208, 910, 1262, outline="#333")
        self._t(490, 1280, "Подпись:", size=9)

    def _draw_metric_block(self, x: int, y: int) -> None:
        defect = self.defect or {}
        rows = [
            ("Кол. отражений луча M", defect.get("defect_m", "0") or "0"),
            ("Глубина дефекта Y, мм", self._fmt1(defect.get("defect_y", 0.0))),
            ("Расст.до проекции деф. X, мм", self._fmt1(defect.get("defect_x", 0.0))),
            ("Расстояние по лучу R, мм", self._fmt1(defect.get("defect_r", 0.0))),
            ("Коэф. выявляемости, дБ", defect.get("detectability_db", "")),
        ]
        for i, (k, v) in enumerate(rows):
            yy = y + i * 22
            self._t(x, yy, k, size=9)
            self._t(x + 230, yy, v, size=9)

    def _draw_native_graph(self) -> None:
        c = self.graph_canvas
        c.delete("all")
        w, h = 360, 230
        ml, mr, mt, mb = 14, 14, 12, 28
        pw, ph = w - ml - mr, h - mt - mb
        c.create_rectangle(ml, mt, w - mr, h - mb, outline="#222")
        for i in range(1, 9):
            x = ml + pw * i / 10
            c.create_line(x, mt, x, h - mb, fill="#cfcfcf", dash=(1, 8))
        for i in range(1, 6):
            y = mt + ph * i / 7
            c.create_line(ml, y, w - mr, y, fill="#cfcfcf", dash=(1, 8))
        if "samples" not in self.graph:
            c.create_text(w // 2, h // 2, text=self.graph.get("error", "Нет графика"), fill="#555")
            return
        samples = self.graph.get("samples") or []
        if not samples:
            return
        baseline_y = h - mb - 20
        c.create_line(ml, baseline_y, w - mr, baseline_y, fill="#777")
        def x_of_i(i: int) -> float:
            return ml + (i / max(1, len(samples) - 1)) * pw
        def y_of_sample(s: int) -> float:
            amp = int(s) - GRAPH_BASELINE
            return baseline_y - (amp / 180.0) * (ph - 10)
        pts = []
        for i, s in enumerate(samples):
            pts.extend((x_of_i(i), y_of_sample(s)))
        if len(pts) >= 4:
            c.create_line(*pts, fill="#111", width=1)
        # Draw a simple native-like cursor/zone marker if zone coordinates are available.
        try:
            duration = int(self.zones.get("duration_t10") or self.setting_params.get("duration_t10") or 7920)
            raw_x = int(self.zones.get("vs1_start_raw", 0) or 0)
            if raw_x:
                x = ml + raw_x / max(1, duration) * pw
                c.create_line(x, mt + 8, x, h - mb, fill="#333")
                c.create_line(x - 8, (mt + h - mb) // 2, x + 8, (mt + h - mb) // 2, fill="#333")
        except Exception:
            pass

    def _draw_settings_block(self, x: int, y: int) -> None:
        self._t(x, y, "О С Н О В Н Ы Е  П А Р А М Е Т Р Ы  Н А С Т Р О Й К И", size=10, bold=True)
        p = self.setting_params or {}
        left = [
            ("Номер настройки", p.get("setting_no", self.setting_no or "")),
            ("Шифр оператора", p.get("operator_code", self._row_get("KODOPERA"))),
            ("Типовой вариант", p.get("typevar_code", self._typevar_code())),
            ("Частота УЗК, МГц", p.get("freq_mhz", "")),
            ("Скорость УЗК, м/с", p.get("sound_speed", "")),
            ("№ ПЭП", p.get("probe_no", "")),
            ("вкл. ПЭП", p.get("probe_enabled", "")),
            ("Угол ввода, град", p.get("angle_deg", "")),
            ("Время в ПЭП, мкс", p.get("probe_time_us", "")),
            ("Толщина, мм", p.get("thickness_mm", "")),
            ("Усиление, дБ", p.get("gain_db", "")),
            ("Треб. чувств., дБ", p.get("required_sens_db", "")),
            ("Факт. чувств., дБ", p.get("actual_sens_db", "")),
            ("Развертка", p.get("sweep_type", "")),
            ("Длительность", p.get("sweep_duration", "")),
            ("W-развертка", p.get("w_sweep_enabled", "")),
            ("Огибающая", p.get("envelope_enabled", "")),
            ("Начало ВС1", p.get("vs1_start", "")),
            ("Конец ВС1", p.get("vs1_end", "")),
            ("Метод ВС1", p.get("vs1_method", "")),
        ]
        right = [
            ("Порог ВС1, %", p.get("vs1_threshold_pct", "")),
            ("Начало ВС2", p.get("vs2_start", "")),
            ("Конец ВС2", p.get("vs2_end", "")),
            ("Метод ВС2", p.get("vs2_method", "")),
            ("Порог ВС2, %", p.get("vs2_threshold_pct", "")),
            ("Вкл. АРУ", p.get("aru_enabled", "-")),
            ("Начало АРУ", p.get("aru_start", "")),
            ("Конец АРУ", p.get("aru_end", "")),
            ("Тип ВРЧ", p.get("vrch_type", "")),
            ("Индикация ВРЧ", p.get("vrch_indication", "")),
            ("Начало ВРЧ", p.get("vrch_start", "")),
            ("Конец ВРЧ", p.get("vrch_end", "")),
            ("Амплитуда ВРЧ, дБ", p.get("vrch_amp_db", "")),
            ("Форма ВРЧ", p.get("vrch_shape", "")),
            ("До ВРЧ, дБ", p.get("before_vrch_db", "")),
            ("После ВРЧ, дБ", p.get("after_vrch_db", "")),
            ("Вкл. доп. усилит.", p.get("extra_gain_enabled", "-")),
            ("Доп усиление, дБ", p.get("extra_gain_db", "")),
        ]
        for i, (k, v) in enumerate(left):
            yy = y + 28 + i * 16
            self._t(x, yy, k, size=8)
            self._t(x + 185, yy, v, size=8)
        for i, (k, v) in enumerate(right):
            yy = y + 28 + i * 16
            self._t(x + 430, yy, k, size=8)
            self._t(x + 625, yy, v, size=8)


APP_TITLE = "Peleng ВАГОННАЯ 6.43 — Idx → 42 → дешифровка"
IDX_DB_DEFAULT = ":memory:"


def bucket_for_addr(addr: int) -> str:
    if 1000 <= addr <= 1999:
        return "settings"
    if 4000 <= addr <= 6999:
        return "protocols"
    if 10000 <= addr <= 29999:
        return "reports"
    if 5000 <= addr <= 5999:
        return "protocols"
    return "other"


def bucket_title(bucket: str) -> str:
    return {
        "reports": "Отчёты",
        "protocols": "Протоколы",
        "settings": "Настройки",
        "other": "Прочее",
    }.get(bucket, bucket)


def human_kind(addr: int) -> str:
    k = kind_for_addr(addr)
    return {
        "setting": "Настройка NASTR2",
        "protocol_short": "A-протокол 4000",
        "protocol_graph": "A-протокол/график 6000",
        "bscan": "B-протокол 5000",
        "report": "Отчёт SHORTPROT2",
        "report_v2": "Отчёт V2",
        "unknown": "Неизвестно",
    }.get(k, k)


def summary_from_fields(addr: int, fields: dict[str, str], params: Optional[dict[str, Any]] = None) -> str:
    k = kind_for_addr(addr)
    if k in ("report", "report_v2"):
        return " | ".join(x for x in [
            fields.get("DATEFORM", ""),
            fields.get("TIMEFORM", ""),
            f"объект={fields.get('NUMOBJ','')}" if fields.get("NUMOBJ") else "",
            f"плавка={fields.get('SMELTING','')}" if fields.get("SMELTING") else "",
            f"деф={fields.get('CODEDEF','')}" if fields.get("CODEDEF") else "",
        ] if x)
    if k in ("protocol_short", "protocol_graph"):
        return " | ".join(x for x in [
            fields.get("DATEFORM", ""),
            fields.get("TIMEFORM", ""),
            f"объект={fields.get('NUMOBJ','')}" if fields.get("NUMOBJ") else "",
            f"TV={fields.get('TYPEVAR','')}" if fields.get("TYPEVAR") else "",
            f"настр={fields.get('SETTING_ADDR','')}" if fields.get("SETTING_ADDR") else "",
            f"граф={fields.get('GRAPH_ADDR','')}" if fields.get("GRAPH_ADDR") else "",
        ] if x)
    if k == "setting":
        p = params or {}
        return " | ".join(x for x in [
            fields.get("DATEFORM", ""),
            fields.get("TIMEFORM", ""),
            f"№={fields.get('SETTING_NO','')}" if fields.get("SETTING_NO") else "",
            f"TV={fields.get('TYPEVAR','')}" if fields.get("TYPEVAR") else "",
            f"угол={p.get('angle_deg','')}" if p.get("angle_deg") not in (None, "") else "",
            f"скорость={p.get('sound_speed','')}" if p.get("sound_speed") not in (None, "") else "",
        ] if x)
    return "RAW сохранён"


class IdxApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1380x820")
        self.minsize(1120, 650)
        
        # Runtime DB must stay in memory.  Do not call os.path.abspath(":memory:"):
        # on Windows that becomes an invalid file path and sqlite raises
        # "unable to open database file".
        runtime_db_path = IDX_DB_DEFAULT if str(IDX_DB_DEFAULT).strip() == ":memory:" else os.path.abspath(IDX_DB_DEFAULT)
        self.db = PelengDB(runtime_db_path)
        self._init_idx_schema()
        self.serial_link: Optional[PelengSerial] = None
        self.header: bytes = b""
        self.device_no: Optional[int] = None
        self.session_id: str = ""
        self.worker: Optional[threading.Thread] = None
        self.uiq: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._build_style()
        self._build_ui()
        self.refresh_ports()
        self.reload_idx_tables()
        self.after(100, self.poll_queue)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_idx_schema(self) -> None:
        self.db.conn.executescript("""
            CREATE TABLE IF NOT EXISTS idx_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_order INTEGER NOT NULL,
                address INTEGER NOT NULL,
                bucket TEXT NOT NULL,
                kind TEXT NOT NULL,
                expected_len INTEGER,
                requested INTEGER NOT NULL DEFAULT 0,
                decoded INTEGER NOT NULL DEFAULT 0,
                raw_len INTEGER,
                status TEXT,
                summary TEXT,
                header_hex TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_catalog_session ON idx_catalog(session_id, source_order);
            CREATE INDEX IF NOT EXISTS idx_catalog_addr ON idx_catalog(address);
        """)
        self.db.conn.commit()

    def _build_style(self) -> None:
        self.configure(bg="#eef3f8")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#eef3f8")
        style.configure("Hero.TFrame", background="#26364d")
        style.configure("HeroTitle.TLabel", background="#26364d", foreground="#ffffff", font=("Segoe UI", 17, "bold"), padding=(16, 12, 16, 0))
        style.configure("HeroSub.TLabel", background="#26364d", foreground="#dbe8ff", font=("Segoe UI", 10), padding=(16, 2, 16, 12))
        style.configure("Hint.TLabel", background="#eef3f8", foreground="#64748b", font=("Segoe UI", 9))
        style.configure("TLabel", background="#eef3f8", foreground="#162033")
        style.configure("TButton", padding=(10, 5), font=("Segoe UI", 9))
        style.configure("Accent.TButton", padding=(12, 6), font=("Segoe UI", 10, "bold"), foreground="#ffffff", background="#2d6cdf")
        style.map("Accent.TButton", background=[("active", "#1f57b7"), ("disabled", "#9eb8e8")])
        style.configure("Danger.TButton", foreground="#ffffff", background="#a33b3b")
        style.configure("Treeview", rowheight=25, font=("Segoe UI", 9), background="#ffffff", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#dfe8f5")

    def _build_ui(self) -> None:
        hero = ttk.Frame(self, style="Hero.TFrame")
        hero.pack(fill=tk.X)
        ttk.Label(hero, text="Peleng ВАГОННАЯ 6.43: Idx-каталог exact-55 и ручной запрос 42", style="HeroTitle.TLabel").pack(fill=tk.X)
        ttk.Label(
            hero,
            text="55 читает только список Idx. Дальше выбранный адрес читается кнопкой: 42 LL HH → RAW → встроенная дешифровка отчёта / протокола / настройки.",
            style="HeroSub.TLabel",
        ).pack(fill=tk.X)

        top = ttk.Frame(self, padding=(12, 10, 12, 6))
        top.pack(fill=tk.X)
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(2, weight=2)

        conn = ttk.LabelFrame(top, text="COM", padding=(10, 8))
        conn.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(conn, text="Порт").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn, textvariable=self.port_var, width=18, state="readonly")
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=(6, 4))
        ttk.Button(conn, text="↻", width=3, command=self.refresh_ports).grid(row=0, column=2, sticky="w")
        ttk.Label(conn, text="Baud").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        ttk.Entry(conn, textvariable=self.baud_var, width=10).grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Label(conn, text="Parity").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.parity_var = tk.StringVar(value=DEFAULT_PARITY)
        ttk.Combobox(conn, textvariable=self.parity_var, width=8, state="readonly", values=["N", "E"]).grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Label(conn, text="по v34 live: 19200 8E1; E оставлен для проверки", style="Hint.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        conn.columnconfigure(1, weight=1)

        actions = ttk.LabelFrame(top, text="Опрос и чтение", padding=(10, 8))
        actions.grid(row=0, column=1, sticky="nsew", padx=8)
        self.clear_idx_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="очищать список Idx перед 55", variable=self.clear_idx_var).grid(row=0, column=0, columnspan=2, sticky="w")
        self.btn_55 = ttk.Button(actions, text="1) Опросить прибор: 55", command=self.start_poll55, style="Accent.TButton")
        self.btn_55.grid(row=1, column=0, sticky="ew", pady=(8, 0), padx=(0, 6))
        self.btn_42 = ttk.Button(actions, text="2) Запросить выбранный: 42 + Idx", command=self.start_fetch_selected)
        self.btn_42.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Открыть дешифровку", command=self.open_selected_detail).grid(row=2, column=0, sticky="ew", pady=(6, 0), padx=(0, 6))
        ttk.Button(actions, text="Закрыть COM", command=self.close_serial).grid(row=2, column=1, sticky="ew", pady=(6, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        info.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self.status_var = tk.StringVar(value=f"БД: {self.db.path}")
        ttk.Label(info, textvariable=self.status_var, style="Hint.TLabel", wraplength=620).pack(anchor="w", fill=tk.X)
        ttk.Label(
            info,
            text="Двойной клик по уже запрошенной строке открывает дешифровку. Если RAW ещё не запрошен, сначала нажми ‘42 + Idx’.",
            style="Hint.TLabel",
            wraplength=620,
        ).pack(anchor="w", fill=tk.X, pady=(6, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 6))
        cols = ["dbid", "order", "address", "kind", "expected", "requested", "raw_len", "decoded", "status", "summary"]
        self.trees: dict[str, ttk.Treeview] = {}
        for bucket, title in (("reports", "Отчёты"), ("protocols", "Протоколы"), ("settings", "Настройки"), ("other", "Прочее")):
            frame = ttk.Frame(self.tabs, padding=8)
            self.tabs.add(frame, text=title)
            tree = ttk.Treeview(frame, columns=cols, show="headings")
            vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
            hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            headings = {
                "dbid": "ID",
                "order": "Idx#",
                "address": "Адрес",
                "kind": "Тип",
                "expected": "Expected",
                "requested": "42?",
                "raw_len": "RAW len",
                "decoded": "Decode?",
                "status": "Статус",
                "summary": "Сводка",
            }
            widths = {"dbid": 60, "order": 70, "address": 90, "kind": 160, "expected": 80, "requested": 55, "raw_len": 70, "decoded": 65, "status": 190, "summary": 520}
            for c in cols:
                tree.heading(c, text=headings[c])
                tree.column(c, width=widths.get(c, 120), anchor="w", stretch=(c == "summary"))
            tree.bind("<Double-1>", lambda _e, b=bucket: self.open_selected_detail(b))
            self.trees[bucket] = tree

        logf = ttk.LabelFrame(self, text="Журнал", padding=6)
        logf.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 10))
        self.log_text = tk.Text(logf, height=8, bg="#0f172a", fg="#e5e7eb", insertbackground="#e5e7eb", wrap=tk.WORD, relief=tk.FLAT)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(logf, command=self.log_text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=sb.set)

    def log(self, message: str) -> None:
        self.log_text.insert(tk.END, f"[{dt.datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)

    def set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_55.configure(state=state)
        self.btn_42.configure(state=state)

    def refresh_ports(self) -> None:
        ports: list[str] = []
        if list_ports is not None:
            ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def make_serial_config(self) -> SerialConfig:
        port = self.port_var.get().strip()
        if not port:
            raise RuntimeError("Не выбран COM-порт")
        try:
            baud = int(self.baud_var.get().strip() or DEFAULT_BAUD)
        except ValueError:
            baud = DEFAULT_BAUD
        parity = (self.parity_var.get().strip().upper() or DEFAULT_PARITY)
        return SerialConfig(port=port, baud=baud, parity=parity, timing_profile=False, timing_byte_mode=False)

    def ensure_serial(self) -> PelengSerial:
        if self.serial_link is not None:
            try:
                if getattr(self.serial_link.ser, "is_open", False):
                    return self.serial_link
            except Exception:
                pass
        self.serial_link = PelengSerial(self.make_serial_config())
        return self.serial_link

    def close_serial(self) -> None:
        if self.serial_link is not None:
            try:
                self.serial_link.close()
            finally:
                self.serial_link = None
            self.log("COM закрыт")

    def selected_tree(self) -> Optional[ttk.Treeview]:
        tab = self.tabs.select()
        for tree in self.trees.values():
            if str(tree.master) == tab:
                return tree
        # Tk returns frame path, so compare the notebook tab child path.
        for bucket, tree in self.trees.items():
            if str(tree.master) == str(self.nametowidget(tab)):
                return tree
        return None

    def selected_addr(self) -> Optional[int]:
        tree = self.selected_tree()
        if tree is None:
            return None
        sel = tree.selection()
        if not sel:
            return None
        vals = tree.item(sel[0], "values")
        try:
            return int(vals[2])
        except Exception:
            return None

    def selected_bucket(self) -> Optional[str]:
        tree = self.selected_tree()
        if tree is None:
            return None
        for bucket, t in self.trees.items():
            if t is tree:
                return bucket
        return None

    def start_poll55(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.set_busy(True)
        self.worker = threading.Thread(target=self._worker_poll55, daemon=True)
        self.worker.start()

    def _worker_poll55(self) -> None:
        try:
            ser = self.ensure_serial()
            self.uiq.put(("log", "TX: 55"))
            header = ser.handshake55(1)
            if len(header) < 0x12:
                raise RuntimeError(f"55 вернул слишком мало байт: {len(header)}")
            ids = parse_header_addresses(header)
            self.header = header
            self.device_no = device_no_from_header(header)
            self.session_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            self._save_idx_list(ids, header)
            counts = header_bucket_counts(ids)
            words_total = getattr(parse_header_addresses, "words_total", 0)
            words_used = getattr(parse_header_addresses, "words_used", 0)
            guard = ""
            if len(header) >= 0x12 and words_total > 0:
                goff = 0x10 + (words_total - 1) * 2
                if goff + 1 < len(header):
                    guard = f", guard=0x{(header[goff] | (header[goff+1] << 8)):04X}"
            self.uiq.put(("log", f"RX 55: {len(header)} bytes, words_total={words_total}, used={words_used}{guard}, Idx={len(ids)}, device={self.device_no}, buckets={counts}"))
            self.uiq.put(("reload", None))
        except Exception as exc:
            self.uiq.put(("error", str(exc)))
        finally:
            self.uiq.put(("busy", False))

    def _save_idx_list(self, ids: list[int], header: bytes) -> None:
        if self.clear_idx_var.get():
            self.db.conn.execute("DELETE FROM idx_catalog")
        created = PelengDB.now()
        header_hex = header.hex()
        for i, addr in enumerate(ids):
            exp = expected_len_for_addr(addr)
            bucket = bucket_for_addr(addr)
            self.db.conn.execute(
                """
                INSERT INTO idx_catalog(session_id,created_at,source_order,address,bucket,kind,expected_len,requested,decoded,raw_len,status,summary,header_hex)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (self.session_id, created, i, int(addr), bucket, kind_for_addr(addr), exp, 0, 0, None, "idx from 55", "", header_hex),
            )
        self.db.conn.commit()

    def start_fetch_selected(self) -> None:
        addr = self.selected_addr()
        if addr is None:
            messagebox.showwarning("42 + Idx", "Выберите строку Idx в одной из таблиц")
            return
        if expected_len_for_addr(addr) is None:
            messagebox.showwarning("42 + Idx", f"Для адреса {addr} нет expected_len в таблице диапазонов")
            return
        if self.worker and self.worker.is_alive():
            return
        self.set_busy(True)
        self.worker = threading.Thread(target=self._worker_fetch42, args=(addr,), daemon=True)
        self.worker.start()

    def _worker_fetch42(self, addr: int) -> None:
        try:
            ser = self.ensure_serial()
            expected = expected_len_for_addr(addr) or 0
            self.uiq.put(("log", f"TX: 42 {addr & 0xff:02X} {(addr >> 8) & 0xff:02X}  addr={addr} expected=0x{expected:04X}"))
            wire = ser.request42_raw(addr, expected)
            record = normalize_record_response(wire, addr, expected)
            status = self._record_status(addr, wire, record, expected)
            base_kind = kind_for_addr(addr)
            save_kind = base_kind if status.startswith("ok") else f"{base_kind}_incomplete"
            raw_id = self.db.save_raw(addr, save_kind, record, self.device_no, self.header, event_raw=wire)
            decoded = False
            summary = ""
            fields: dict[str, str] = {}
            params: dict[str, Any] = {}
            if status.startswith("ok"):
                try:
                    if base_kind in ("report", "report_v2"):
                        fields = decode_report_643(record, addr, self.device_no, strict=False)
                        self.db.save_report(raw_id, addr, fields)
                        decoded = True
                    elif base_kind in ("protocol_short", "protocol_graph"):
                        fields = decode_protocol_ascan_643(record, addr, self.device_no, strict=False)
                        self.db.save_protocol(raw_id, addr, fields)
                        decoded = True
                        try:
                            graph_addr = graph_addr_for_protocol(addr)
                            graph_raw_row = self.db.get_raw_by_addr(graph_addr)
                            setting_addr = protocol_setting_addr_643(record)
                            setting_raw_row = self.db.get_raw_by_addr(setting_addr)
                            diag = diagnose_protocol_643(
                                addr,
                                record,
                                bytes(graph_raw_row["raw"]) if graph_raw_row else None,
                                bytes(setting_raw_row["raw"]) if setting_raw_row else None,
                            )
                            self.db.save_protocol_diagnostic(diag)
                        except Exception:
                            pass
                    elif base_kind == "setting":
                        fields, params = decode_setting_643(record, addr, self.device_no, strict=False)
                        self.db.save_setting(raw_id, addr, fields, params)
                        decoded = True
                    elif base_kind == "bscan":
                        summary = "B-scan RAW сохранён; декодер B-scan в этом UI не встроен"
                    else:
                        summary = "RAW сохранён; декодер для типа не задан"
                except Exception as exc:
                    status = f"decode_error: {exc}"
                    decoded = False
            if decoded:
                summary = summary_from_fields(addr, fields, params)
            if not summary:
                summary = f"wire={len(wire)} record={len(record)}"
            self._update_idx_after_fetch(addr, len(record), decoded, status, summary)
            self.uiq.put(("log", f"RX {addr}: wire={len(wire)} record={len(record)} status={status}; decoded={decoded}"))
            self.uiq.put(("reload", None))
        except Exception as exc:
            self.uiq.put(("error", str(exc)))
        finally:
            self.uiq.put(("busy", False))

    def _record_status(self, addr: int, wire: bytes, record: bytes, expected: int) -> str:
        if not wire:
            return f"empty/no first byte, expected={expected}"
        if is_wire_empty_marker(wire):
            return f"empty marker {wire.hex(' ')}"
        # Оригинал PelengPC сравнивает именно фактическую длину приёма с expected_len.
        # normalize_record_response может отрезать overread до expected, поэтому strict-статус
        # считаем по wire_len, а record используем только для последующей дешифровки.
        if len(wire) < expected:
            return f"short: wire {len(wire)}/{expected}"
        if len(wire) > expected:
            return f"overread: wire {len(wire)}/{expected}"
        if len(record) != expected:
            return f"normalized_len: record {len(record)}/{expected}"
        if not record_addr_matches(record, addr):
            return "bad addr prefix"
        if kind_for_addr(addr) in ("report", "report_v2") and not report_wire_complete(record, addr):
            return report_wire_problem(record, addr)
        return "ok"

    def _update_idx_after_fetch(self, addr: int, raw_len: int, decoded: bool, status: str, summary: str) -> None:
        self.db.conn.execute(
            """
            UPDATE idx_catalog
            SET requested=1, decoded=?, raw_len=?, status=?, summary=?
            WHERE address=?
            """,
            (1 if decoded else 0, raw_len, status, summary, addr),
        )
        self.db.conn.commit()

    def reload_idx_tables(self) -> None:
        for tree in self.trees.values():
            for item in tree.get_children():
                tree.delete(item)
        rows = list(self.db.conn.execute("SELECT * FROM idx_catalog ORDER BY id"))
        for row in rows:
            bucket = row["bucket"] if row["bucket"] in self.trees else "other"
            tree = self.trees[bucket]
            values = [
                row["id"],
                row["source_order"],
                row["address"],
                human_kind(int(row["address"])),
                row["expected_len"] or "",
                "да" if row["requested"] else "",
                row["raw_len"] or "",
                "да" if row["decoded"] else "",
                row["status"] or "",
                row["summary"] or "",
            ]
            tree.insert("", tk.END, values=values)
        counts = {b: len(t.get_children()) for b, t in self.trees.items()}
        self.status_var.set(
            f"БД: {self.db.path} | session={self.session_id or '-'} | Idx: "
            f"отчёты={counts.get('reports',0)}, протоколы={counts.get('protocols',0)}, настройки={counts.get('settings',0)}, прочее={counts.get('other',0)}"
        )

    def open_selected_detail(self, forced_bucket: Optional[str] = None) -> None:
        addr = self.selected_addr()
        if addr is None:
            return
        raw_row = self.db.get_raw_by_addr(addr)
        if not raw_row:
            messagebox.showinfo("Дешифровка", f"Адрес {addr} ещё не запрошен. Нажми ‘42 + Idx’.")
            return
        k = kind_for_addr(addr)
        try:
            if k in ("report", "report_v2"):
                row = self.db.row_by_addr("reports", addr)
                if not row:
                    raw = bytes(raw_row["raw"])
                    fields = decode_report_643(raw, addr, self.device_no, strict=False)
                    self.db.save_report(int(raw_row["id"]), addr, fields)
                    row = self.db.row_by_addr("reports", addr)
                if row:
                    ReportDetail(self, row, bytes(raw_row["raw"]))
                return
            if k in ("protocol_short", "protocol_graph"):
                row = self.db.row_by_addr("protocols", addr)
                if not row:
                    raw = bytes(raw_row["raw"])
                    fields = decode_protocol_ascan_643(raw, addr, self.device_no, strict=False)
                    self.db.save_protocol(int(raw_row["id"]), addr, fields)
                    row = self.db.row_by_addr("protocols", addr)
                if row:
                    ProtocolDetail(self, self.db, row)
                return
            if k == "setting":
                row = self.db.row_by_addr("settings", addr)
                if not row:
                    raw = bytes(raw_row["raw"])
                    fields, params = decode_setting_643(raw, addr, self.device_no, strict=False)
                    self.db.save_setting(int(raw_row["id"]), addr, fields, params)
                    row = self.db.row_by_addr("settings", addr)
                if row:
                    SettingDetail(self, row, bytes(raw_row["raw"]))
                return
            RawDetail(self, raw_row)
        except Exception as exc:
            messagebox.showerror("Дешифровка", str(exc))

    def poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.uiq.get_nowait()
                if kind == "log":
                    self.log(str(payload))
                elif kind == "error":
                    self.log(f"ОШИБКА: {payload}")
                    messagebox.showerror("Peleng UI", str(payload))
                elif kind == "reload":
                    self.reload_idx_tables()
                elif kind == "busy":
                    self.set_busy(bool(payload))
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def on_close(self) -> None:
        self.close_serial()
        try:
            self.db.conn.close()
        except Exception:
            pass
        self.destroy()



class SimpleUserApp(IdxApp):
    """Упрощённый пользовательский UI.

    Один сценарий:
      1) пользователь выбирает, что получить: отчёты / протоколы / настройки / всё;
      2) кнопка «Получить данные» делает 55, сохраняет Idx;
      3) автоматически запрашивает выбранные Idx через 42 LL HH;
      4) таблицы сортируются по вкладкам, двойной клик открывает дешифровку.
    """

    def __init__(self) -> None:
        super().__init__()
        self.title("Peleng ВАГОННАЯ — быстрый сбор данных / 218 отчётов")
        try:
            self.geometry("1180x760")
            self.minsize(980, 600)
        except Exception:
            pass

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=(14, 12, 14, 10))
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=16, state="readonly")
        self.port_combo.grid(row=0, column=0, sticky="w")
        ttk.Button(top, text="↻", width=3, command=self.refresh_ports).grid(row=0, column=1, sticky="w", padx=(6, 16))

        # Технические параметры оставлены скрытыми/дефолтными для обычного пользователя.
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        self.parity_var = tk.StringVar(value="E")
        self.clear_idx_var = tk.BooleanVar(value=True)

        self.mode_var = tk.StringVar(value="reports")
        mode_box = ttk.Frame(top)
        mode_box.grid(row=0, column=2, sticky="e")
        for value, text in (
            ("reports", "Отчёты"),
            ("protocols", "Протоколы"),
            ("settings", "Настройки"),
            ("all", "Всё"),
        ):
            ttk.Radiobutton(mode_box, text=text, value=value, variable=self.mode_var).pack(side=tk.LEFT, padx=(0, 10))

        self.btn_get = ttk.Button(top, text="Получить данные", style="Accent.TButton", command=self.start_get_data)
        self.btn_get.grid(row=0, column=3, sticky="e", padx=(10, 0))
        ttk.Button(top, text="Закрыть", command=self.close_serial).grid(row=0, column=4, sticky="e", padx=(8, 0))

        self.status_var = tk.StringVar(value="Выберите COM-порт и нажмите «Получить данные»")
        ttk.Label(root, textvariable=self.status_var, style="Hint.TLabel").grid(row=1, column=0, sticky="ew", pady=(10, 8))

        self.tabs = ttk.Notebook(root)
        self.tabs.grid(row=2, column=0, sticky="nsew")
        self.trees: dict[str, ttk.Treeview] = {}
        cols = ["address", "date", "object", "result", "status"]
        for bucket, title in (("reports", "Отчёты"), ("protocols", "Протоколы"), ("settings", "Настройки"), ("other", "Прочее")):
            frame = ttk.Frame(self.tabs, padding=8)
            self.tabs.add(frame, text=title)
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
            vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            headings = {
                "address": "Адрес",
                "date": "Дата / время",
                "object": "Объект",
                "result": "Данные",
                "status": "Статус",
            }
            widths = {"address": 90, "date": 150, "object": 260, "result": 480, "status": 150}
            for c in cols:
                tree.heading(c, text=headings[c])
                tree.column(c, width=widths[c], anchor="w", stretch=(c in ("object", "result")))
            tree.bind("<Double-1>", lambda _e, b=bucket: self.open_selected_detail(b))
            self.trees[bucket] = tree

        bottom = ttk.Frame(root)
        bottom.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(bottom, text="Открыть", command=self.open_selected_detail).pack(side=tk.LEFT)
        self.progress_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.progress_var, style="Hint.TLabel").pack(side=tk.LEFT, padx=(12, 0))

        # Совместимость с базовыми методами IdxApp.
        self.btn_55 = self.btn_get
        self.btn_42 = self.btn_get
        self.log_text = None

    def log(self, message: str) -> None:
        # Для обычного UI не показываем технический журнал, только короткое состояние.
        self.progress_var.set(str(message))

    def set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_get.configure(state=state)

    def selected_tree(self) -> Optional[ttk.Treeview]:
        tab = self.tabs.select()
        try:
            widget = self.nametowidget(tab)
        except Exception:
            widget = None
        for tree in self.trees.values():
            if widget is not None and tree.master is widget:
                return tree
            if str(tree.master) == str(tab):
                return tree
        return None

    def selected_addr(self) -> Optional[int]:
        tree = self.selected_tree()
        if tree is None:
            return None
        sel = tree.selection()
        if not sel:
            return None
        vals = tree.item(sel[0], "values")
        try:
            return int(vals[0])
        except Exception:
            return None

    def start_get_data(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.set_busy(True)
        self.progress_var.set("Опрос прибора...")
        self.worker = threading.Thread(target=self._worker_get_data, daemon=True)
        self.worker.start()

    def _wanted(self, addr: int) -> bool:
        mode = self.mode_var.get()
        k = kind_for_addr(addr)
        if mode == "all":
            return k in ("report", "report_v2", "protocol_short", "protocol_graph", "bscan", "setting")
        if mode == "reports":
            return k in ("report", "report_v2")
        if mode == "protocols":
            return k in ("protocol_short", "protocol_graph", "bscan")
        if mode == "settings":
            return k == "setting"
        return False

    @staticmethod
    def _fmt_elapsed(seconds: float) -> str:
        seconds = max(0, float(seconds))
        m, sec = divmod(int(seconds + 0.5), 60)
        if m:
            return f"{m} мин {sec:02d} с"
        return f"{sec} с"

    def _worker_get_data(self) -> None:
        overall_started = time.perf_counter()
        try:
            ser = self.ensure_serial()
            self.uiq.put(("progress", "Опрос 55... прошло 0 с"))
            header = ser.handshake55(1)
            if len(header) < 0x12:
                raise RuntimeError(f"Прибор вернул слишком мало байт на 55: {len(header)}")
            ids = parse_header_addresses(header)
            self.header = header
            self.device_no = device_no_from_header(header)
            self.session_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            self._save_idx_list(ids, header)
            self.uiq.put(("reload", None))

            targets = [a for a in ids if self._wanted(a) and expected_len_for_addr(a) is not None]
            total = len(targets)
            if total == 0:
                self.uiq.put(("log", "В выбранном режиме нет адресов для запроса"))
                return

            ok = 0
            decoded = 0
            read_started = time.perf_counter()
            expected_s = total / BENCHMARK_218_RECORDS_PER_SEC if BENCHMARK_218_RECORDS_PER_SEC > 0 else 0
            self.uiq.put(("progress", f"Найдено {total} записей. Ожидаемое время: ~{self._fmt_elapsed(expected_s)}"))
            self.db.begin_bulk()
            try:
                for i, addr in enumerate(targets, 1):
                    elapsed_read = time.perf_counter() - read_started
                    elapsed_total = time.perf_counter() - overall_started
                    rate = (i - 1) / elapsed_read if elapsed_read > 0 and i > 1 else 0.0
                    eta = (total - i + 1) / rate if rate > 0 else (total - i + 1) / BENCHMARK_218_RECORDS_PER_SEC
                    self.uiq.put((
                        "progress",
                        f"Запрос {i}/{total}: {addr} | прошло {self._fmt_elapsed(elapsed_total)} | осталось ~{self._fmt_elapsed(eta)}"
                    ))
                    try:
                        result = self._fetch_and_decode_addr(ser, addr)
                        if result.get("ok"):
                            ok += 1
                        if result.get("decoded"):
                            decoded += 1
                    except Exception as exc:
                        self._update_idx_after_fetch(addr, 0, False, f"ошибка: {exc}", "")
                    if i % UI_RELOAD_EVERY == 0 or i == total:
                        # Commit in batches so the UI can show progress and data is not
                        # held entirely in memory, but avoid one commit per record.
                        self.db.end_bulk()
                        self.db.begin_bulk()
                        self.uiq.put(("reload", None))
            finally:
                self.db.end_bulk()
            read_elapsed = time.perf_counter() - read_started
            total_elapsed = time.perf_counter() - overall_started
            speed = total / read_elapsed if read_elapsed > 0 else 0.0
            self.uiq.put(("reload", None))
            self.uiq.put((
                "log",
                f"Готово за {self._fmt_elapsed(total_elapsed)}: запрошено {total}, получено {ok}, "
                f"дешифровано {decoded}, скорость {speed:.2f} зап/с"
            ))
        except Exception as exc:
            self.uiq.put(("error", str(exc)))
        finally:
            self.uiq.put(("busy", False))

    def _fetch_and_decode_addr(self, ser: PelengSerial, addr: int) -> dict[str, Any]:
        expected = expected_len_for_addr(addr) or 0
        wire = ser.request42_raw(addr, expected)
        record = normalize_record_response(wire, addr, expected)
        status = self._record_status(addr, wire, record, expected)
        base_kind = kind_for_addr(addr)
        save_kind = base_kind if status.startswith("ok") else f"{base_kind}_incomplete"
        raw_id = self.db.save_raw(addr, save_kind, record, self.device_no, self.header, event_raw=wire)
        decoded = False
        fields: dict[str, str] = {}
        params: dict[str, Any] = {}
        summary = ""

        if status.startswith("ok"):
            try:
                if base_kind in ("report", "report_v2"):
                    fields = decode_report_643(record, addr, self.device_no, strict=False)
                    self.db.save_report(raw_id, addr, fields)
                    decoded = True
                elif base_kind in ("protocol_short", "protocol_graph"):
                    fields = decode_protocol_ascan_643(record, addr, self.device_no, strict=False)
                    self.db.save_protocol(raw_id, addr, fields)
                    decoded = True
                    try:
                        graph_addr = graph_addr_for_protocol(addr)
                        graph_raw_row = self.db.get_raw_by_addr(graph_addr)
                        setting_addr = protocol_setting_addr_643(record)
                        setting_raw_row = self.db.get_raw_by_addr(setting_addr)
                        diag = diagnose_protocol_643(
                            addr,
                            record,
                            bytes(graph_raw_row["raw"]) if graph_raw_row else None,
                            bytes(setting_raw_row["raw"]) if setting_raw_row else None,
                        )
                        self.db.save_protocol_diagnostic(diag)
                    except Exception:
                        pass
                elif base_kind == "setting":
                    fields, params = decode_setting_643(record, addr, self.device_no, strict=False)
                    self.db.save_setting(raw_id, addr, fields, params)
                    decoded = True
                elif base_kind == "bscan":
                    summary = "B-scan сохранён"
                else:
                    summary = "Сохранено"
            except Exception as exc:
                status = f"ошибка дешифровки: {exc}"

        if decoded:
            summary = summary_from_fields(addr, fields, params)
        if not summary:
            summary = "получено" if status.startswith("ok") else status
        self._update_idx_after_fetch(addr, len(record), decoded, status, summary)
        return {"ok": status.startswith("ok"), "decoded": decoded, "status": status}

    def _display_values_for_addr(self, row: sqlite3.Row) -> list[Any]:
        addr = int(row["address"])
        k = kind_for_addr(addr)
        status = str(row["status"] or "")
        summary = str(row["summary"] or "")
        date_time = ""
        obj = ""
        data = summary
        try:
            if k in ("report", "report_v2"):
                r = self.db.row_by_addr("reports", addr)
                if r:
                    date_time = " ".join(x for x in [r["DATEFORM"], r["TIMEFORM"]] if x)
                    obj = str(r["NUMOBJ"] or "")
                    data = " | ".join(x for x in [
                        f"Плавка {r['SMELTING']}" if "SMELTING" in r.keys() and r["SMELTING"] else "",
                        f"Дефектов {r['CODEDEF']}" if r["CODEDEF"] else "",
                        f"Протокол {r['PROTOCOL']}" if r["PROTOCOL"] else "",
                    ] if x) or summary
            elif k in ("protocol_short", "protocol_graph"):
                r = self.db.row_by_addr("protocols", addr)
                if r:
                    date_time = " ".join(x for x in [r["DATEFORM"], r["TIMEFORM"]] if x)
                    obj = str(r["NUMOBJ"] or "")
                    data = " | ".join(x for x in [
                        f"Тип {r['TYPEVAR']}" if r["TYPEVAR"] else "",
                        f"Настройка {r['SETTING_ADDR']}" if r["SETTING_ADDR"] else "",
                        f"График {r['GRAPH_ADDR']}" if r["GRAPH_ADDR"] else "",
                        f"Дефект {r['DEFEKT']}" if r["DEFEKT"] else "",
                    ] if x) or summary
            elif k == "setting":
                r = self.db.row_by_addr("settings", addr)
                if r:
                    date_time = " ".join(x for x in [r["DATEFORM"], r["TIMEFORM"]] if x)
                    obj = f"№ {r['SETTING_NO']}" if r["SETTING_NO"] else ""
                    data = f"Типовой вариант {r['TYPEVAR']}" if r["TYPEVAR"] else summary
        except Exception:
            pass


    def reload_idx_tables(self) -> None:
        for tree in self.trees.values():
            for item in tree.get_children():
                tree.delete(item)
        rows = list(self.db.conn.execute("SELECT * FROM idx_catalog ORDER BY address"))
        for row in rows:
            bucket = row["bucket"] if row["bucket"] in self.trees else "other"
            self.trees[bucket].insert("", tk.END, values=self._display_values_for_addr(row))
        counts = {b: len(t.get_children()) for b, t in self.trees.items()}
        self.status_var.set(
            f"Отчёты: {counts.get('reports',0)}   Протоколы: {counts.get('protocols',0)}   "
            f"Настройки: {counts.get('settings',0)}   Прочее: {counts.get('other',0)}"
        )

    def open_selected_detail(self, forced_bucket: Optional[str] = None) -> None:
        addr = self.selected_addr()
        if addr is None:
            return
        raw_row = self.db.get_raw_by_addr(addr)
        if not raw_row:
            messagebox.showinfo("Данные", "Эта запись ещё не получена. Нажмите «Получить данные».")
            return
        return super().open_selected_detail(forced_bucket)

    def poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.uiq.get_nowait()
                if kind == "log":
                    self.log(str(payload))
                elif kind == "progress":
                    self.progress_var.set(str(payload))
                elif kind == "error":
                    self.progress_var.set(f"Ошибка: {payload}")
                    messagebox.showerror("Peleng", str(payload))
                elif kind == "reload":
                    self.reload_idx_tables()
                elif kind == "busy":
                    self.set_busy(bool(payload))
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)



# ---------------------------------------------------------------------------
# Native-like UI (PelengPC-style main table + report sheet on double click)
# ---------------------------------------------------------------------------

_NATIVE_REPORT_COLS = [
    ("num", "№ записи", 92),
    ("date", "Дата", 110),
    ("time", "Время", 84),
    ("operator", "Имя оператора", 135),
    ("version", "Версия ПО", 104),
    ("device", "№ прибора", 100),
    ("typevar", "Типовой", 92),
    ("object", "№ объекта", 150),
    ("defects", "Количество деф", 118),
    ("protocol", "Протокол", 96),
]

_NATIVE_PROTOCOL_COLS = [
    ("num", "№ записи", 92),
    ("date", "Дата", 110),
    ("time", "Время", 84),
    ("operator", "Имя оператора", 135),
    ("version", "Версия ПО", 104),
    ("device", "№ прибора", 100),
    ("typevar", "Типовой", 92),
    ("object", "№ объекта", 150),
    ("setting", "№ настройки", 110),
    ("defect", "Дефект", 96),
]

_NATIVE_SETTING_COLS = [
    ("num", "№ записи", 92),
    ("date", "Дата", 110),
    ("time", "Время", 84),
    ("operator", "Имя оператора", 135),
    ("version", "Версия ПО", 104),
    ("device", "№ прибора", 100),
    ("setting", "№ настройки", 110),
    ("typevar", "Типовой", 110),
]




# Native basket semantics from PelengPC reverse:
#   raw Idx is kept hidden in Treeview tag addr:<full_idx>.
#   visible № записи is decoder NUMKOD/container-style number, not raw Idx.
#   reports use addr % 10000 (10101 -> 101, 13401 -> 3401);
#   settings/protocols use addr % 1000.
def native_visible_num_for_addr(addr: int) -> str:
    if 10000 <= int(addr) <= 29999:
        return str(int(addr) % 10000)
    return str(int(addr) % 1000)


def native_report_container_base(addr: int) -> int:
    return (int(addr) // 100) * 100

def _native_num_from_report_row(row: sqlite3.Row, addr: int) -> str:
    try:
        v = str(row["NUMKOD"] or "").strip()
        return v or str(addr % 10000)
    except Exception:
        return native_visible_num_for_addr(addr)


def _short_typevar(v: Any) -> str:
    s = str(v or "").strip()
    # Display like native grid: just 731/834 when available.
    token = s.split()[0] if s else ""
    return token if token.isdigit() else s


def _native_obj_type_from_typevar(v: Any) -> str:
    try:
        tv = int(_short_typevar(v))
    except Exception:
        return ""
    info = typevar_info_643(tv)
    obj = (info.get("object") or "").strip()
    detail = (info.get("detail") or "").strip()
    if tv // 100 == 7:
        return obj or "ось РУ1Ш"
    if tv // 100 == 8:
        return obj or "колесо"
    return obj or detail


def _native_report_body(raw: bytes, addr: int) -> bytes:
    try:
        body, _layout = report_body_and_layout(raw, addr)
        return body
    except Exception:
        return raw or b""


def _u8_any(buf: bytes, *offs: int, default: int = -1) -> int:
    for off in offs:
        if 0 <= off < len(buf):
            return int(buf[off])
    return default


def _le16_any(buf: bytes, *offs: int, default: int = 0) -> int:
    for off in offs:
        if 0 <= off + 1 < len(buf):
            return safe_le16(buf, off, default)
    return default


def _native_side_text(v: int) -> str:
    # Live variants differ; keep short native-like words.
    return {0: "обе", 1: "прав", 2: "лев", 3: "обе"}.get(int(v), "")


def _native_neck_text(v: int) -> str:
    return {0: "с кольцами", 1: "без колец", 2: "с буксой", 3: "с буксой"}.get(int(v), "")


def _native_rim_text(v: int) -> str:
    if not v:
        return "-"
    # Some rows store thickness in mm or deci-mm; use native-style category.
    val = v / 10.0 if v > 100 else float(v)
    if val >= 50:
        return "выше 50мм"
    if val >= 40:
        return "более 40мм"
    return "менее 40мм"


def _native_yes_no(v: int, empty_dash: bool = True) -> str:
    if v in (0, 255):
        return "-" if empty_dash else "нет"
    return "есть" if v in (1, 2, 3) else "нет"


def _native_report_raw_for_row(db: PelengDB, row: sqlite3.Row) -> bytes:
    """Return the clean 0x42 payload for a report row, if it is present in DB."""
    try:
        raw_row = db.get_raw_by_addr(int(row["address"]))
        if raw_row is not None and raw_row["raw"] is not None:
            return bytes(raw_row["raw"])
    except Exception:
        pass
    return b""


def _fmt_le16_if_plausible(buf: bytes, off: int, lo: int = 1, hi: int = 9999) -> str:
    v = safe_le16(buf, off, 0)
    return str(v) if lo <= v <= hi else ""


def _fmt_year_candidate(buf: bytes, *offs: int) -> str:
    for off in offs:
        if off + 1 < len(buf):
            v = safe_le16(buf, off, 0)
            if 1950 <= v <= 2035:
                return str(v)
            if 20 <= v <= 35:
                return str(2000 + v)
        if off < len(buf):
            b = safe_u8(buf, off, 255)
            if 20 <= b <= 35:
                return str(2000 + b)
    return ""


def _enum_text(value: int, table: dict[int, str]) -> str:
    try:
        return table.get(int(value), "")
    except Exception:
        return ""


def _native_report_digit_field_exact(raw: bytes, off: int, length: int) -> str:
    """zapis2 FUN_0042409A digit field: read bytes backwards.

    Values 0..9 are real digits, including 0x00.  Previous builds treated
    0x00 as padding and therefore destroyed native values like
    ``000566666612``.  Only 0x0A/0xFF/space-like bytes are treated as padding.
    If the field is all zeros, show one ``0`` like the original report sheet.
    """
    if not raw or off < 0 or off + length > len(raw):
        return ""
    chars: list[str] = []
    for i in range(length - 1, -1, -1):
        b = raw[off + i]
        if 0 <= b <= 9:
            chars.append(str(b))
        elif b in (0x0A, 0x0B, 0x0C, 0xFF, 0x20):
            continue
    s = "".join(chars)
    if s and set(s) == {"0"}:
        return "0"
    return s


def _native_report_sheet_typevar(raw: bytes) -> int:
    # zapis2 descriptor complex fields use full-buffer word at 0x49.  The
    # SAFEARRAY passed to zapis2 has a 0x20-byte prefix, so clean 0x42 payload
    # offset is 0x49 - 0x20 = 0x29.
    v = safe_le16(raw, 0x29, 0) if raw else 0
    if 0 < v < 5000:
        return int(v)
    # fallback to old candidates, but never let it corrupt the exact path
    return detect_typevar_code(raw, (0x29, 0x28, 0x2A)) if raw else 0


def _native_report_side(byte_value: int) -> str:
    return {
        0: "нет",
        1: "лев",
        2: "прав",
        3: "А",
        4: "Б",
        5: "обе",
    }.get(int(byte_value), "")


def _native_report_neck(byte_value: int, typevar: int) -> str:
    # FUN_0041CEF4(byte, typevar): for wheel/bandage-like groups returns '-'.
    if typevar // 100 in (4, 5, 6, 8, 9):
        return "-"
    return {0: "открытая", 1: "с кольцами", 2: "с буксой"}.get(int(byte_value), "")


def _native_report_rim(byte_value: int, typevar: int) -> str:
    # FUN_0041CF78(byte, typevar)
    g = typevar // 100
    if g in (1, 2, 3, 4, 6, 7):
        return "-"
    if g == 9 and typevar not in (0x385, 0x386, 0x387):
        return "-"
    return {1: "более 40мм", 2: "менее 40мм", 3: "выше 50мм", 4: "ниже 50мм"}.get(int(byte_value), "")


def _native_report_wheel_turn(flag_byte: int, typevar: int) -> str:
    # FUN_0041D03F(flag, typevar): bit0 for wheel turning.
    g = typevar // 100
    if g in (1, 2, 3, 4, 6, 7):
        return "-"
    if g == 9 and typevar not in (0x385, 0x386, 0x387):
        return "-"
    return "есть" if (int(flag_byte) & 1) else "нет"


def _native_report_crest(flag_byte: int, typevar: int) -> str:
    # FUN_0041D0CA(flag, typevar): bit1 for crest/ridge presence.
    g = typevar // 100
    if g in (1, 2, 3, 4, 6, 7):
        return "-"
    if g == 9 and typevar not in (0x385, 0x386, 0x387):
        return "-"
    return "есть" if (int(flag_byte) & 2) else "нет"


def _native_report_detail_values(db: PelengDB, row: sqlite3.Row) -> dict[str, str]:
    """Exact native report-sheet decode, isolated from main-grid decoder.

    Reverse correction: zapis2 receives a SAFEARRAY record with a 0x20-byte
    prefix before the clean 0x42 payload.  The descriptor table
    PTR_DAT_0050C8E8+0x0AF8 uses offsets in that SAFEARRAY buffer.  Therefore
    every descriptor field for the row table maps to clean payload as:

        clean_record_offset = zapis2_descriptor_offset - 0x20

    This fixes the previous bad experiments that used passport-base or -0x10.
    The main window/basket remains untouched; only the double-click sheet uses
    this exact map.
    """
    addr = int(row["address"])
    raw = _native_report_raw_for_row(db, row) or b""

    def s(name: str) -> str:
        try:
            return str(row[name] or "").strip()
        except Exception:
            return ""

    # Date/time: keep saved decoder value if it is complete, otherwise decode
    # from report-specific live layout.  Older UI code displayed ``date[-8:]``
    # and produced values like ``.04.2026``; the sheet renderer now formats
    # DD.MM.YYYY explicitly through _native_report_display_date().
    date_s = s("DATEFORM")
    time_s = s("TIMEFORM")
    if raw:
        d0, t0 = live_report_date_time(raw, addr)
        if not d0:
            d0, t0 = report_date_time(raw)
        if not d0:
            d0, t0 = best_datetime(raw, (0x07, 0x06, 0x08), bcd_year=True)
        if d0 and not d0.startswith("00."):
            date_s, time_s = d0, t0 or time_s

    # Core row exact descriptor offsets from PTR_DAT_0050C8E8 row subtable.
    typevar = _native_report_sheet_typevar(raw)
    if not typevar:
        try:
            typevar = int(_short_typevar(s("TYPEVAR")))
        except Exception:
            typevar = 0
    obj_type = _native_obj_type_from_typevar(str(typevar)) or typevar_display(typevar)

    numobj = _native_report_digit_field_exact(raw, 0x11, 0x0C) if raw else ""
    smelting = _native_report_digit_field_exact(raw, 0x35, 0x07) if raw else ""
    if not numobj:
        numobj = s("NUMOBJ")
    if not smelting:
        smelting = s("SMELTING")

    factory = str(safe_le16(raw, 0x3C, 0)) if raw and safe_le16(raw, 0x3C, 0) else ""
    year_v = safe_le16(raw, 0x3E, 0) if raw else 0
    year = str(year_v) if 1900 <= year_v <= 2099 else (str(year_v) if 1900 <= year_v + 2000 <= 2099 else "")

    side = _native_report_side(safe_u8(raw, 0x40, 255)) if raw else ""
    neck = _native_report_neck(safe_u8(raw, 0x41, 255), typevar) if raw else ""
    rim = _native_report_rim(safe_u8(raw, 0x42, 255), typevar) if raw else ""
    flag = safe_u8(raw, 0x43, 0) if raw else 0
    wheel_turn = _native_report_wheel_turn(flag, typevar) if raw else ""
    crest = _native_report_crest(flag, typevar) if raw else ""
    # Native report sheet hides axle-only columns for wheels and wheel-only
    # columns for axles.  This prevents plausible but wrong text such as
    # "с кольцами" in the wheel neck column.
    obj_l = obj_type.lower()
    if "колес" in obj_l:
        neck = ""
    if "ось" in obj_l:
        rim = "-"
        wheel_turn = "-"
        crest = "-"

    defects = ""
    if raw:
        vdef = safe_u8(raw, 0x0C, 255)
        defects = str(vdef) if 0 <= vdef <= 99 else ""
    if not defects:
        defects = s("CODEDEF")

    # Header sheet setting number.  In native screenshots this matches a small
    # value in the report payload; prefer the live-specific field, then exact
    # z-table fallback if present.
    setting_no = ""
    if raw:
        setting_no = _fmt_le16_if_plausible(raw, 0x0D, 1, 999) or _fmt_le16_if_plausible(raw, 0x1D, 1, 9999)

    return {
        "date": date_s,
        "time": time_s,
        "obj_type": obj_type,
        "numobj": numobj,
        "smelting": smelting,
        "factory": factory,
        "year": year,
        "side": side,
        "neck": neck,
        "rim": rim,
        "wheel_turn": wheel_turn,
        "crest": crest,
        "defects": defects,
        "setting_no": setting_no,
    }

#
# Original PelengPC keeps two levels:
#   1) raw 55 Idx catalogue at FormReadData+0x30C;
#   2) visible/request basket at +0x3B4.
# For report ranges 10000..29999 the basket contains one container per
# base=(addr//100)*100, even when the container has exactly one child row.
# Double-click expands/loads all child rows base+1..base+max_row that were
# present in the original 55 list.  This block implements that presentation
# without changing the transport/decoder core above.
# ---------------------------------------------------------------------------


def _normalize_55_header_bytes(blob: bytes | None) -> bytes:
    """Return the real 16-byte 55/session header from any stored header blob.

    Older experimental builds sometimes saved shifted or oversized header_hex.
    Native meta in the main grid must be taken from the original 55 header:
      header16[0..1] = device number
      header16[4..5] = firmware version

    Prefer candidates that look like the observed live header:
      4C 11 01 00 06 2A ... for device 4428 / version 06.42.
    """
    b = bytes(blob or b"")
    if not b:
        return b""

    def score(c: bytes) -> int:
        if len(c) < 16:
            return -9999
        dev = safe_le16(c, 0, 0)
        maj, minor = int(c[4]), int(c[5])
        flags = int(c[2])
        sc = 0
        if 1 <= dev <= 9999:
            sc += 20
        # Some lab dumps had >9999 device-like words; allow but score lower.
        elif 1 <= dev <= 65535:
            sc += 3
        if maj == 6 and 0 <= minor <= 99:
            sc += 40
        elif 1 <= maj <= 9 and 0 <= minor <= 99:
            sc += 15
        # Known live flags are small bitfields, often 0/1/2/4.
        if flags in (0, 1, 2, 3, 4, 5, 6, 7):
            sc += 5
        # Observed UD2/UD3 headers often start with a plausible nonzero device word,
        # then two control/flag bytes, then version 06.xx.
        if maj == 6 and minor in (42, 43):
            sc += 25
        return sc

    # If the blob itself starts at header16, use it.
    best = b[:16]
    best_score = score(best)
    # Otherwise scan a small prefix.  This handles accidental prefixes and
    # stale shifted blobs without letting payload bytes 06 2A become device 10758.
    for off in range(0, min(len(b) - 15, 64)):
        c = b[off:off + 16]
        sc = score(c) - off  # prefer earlier if equal
        if sc > best_score:
            best, best_score = c, sc
    if best_score < 20:
        return b[:16] if len(b) >= 16 else b
    return best


def _native_header_version(header: bytes) -> str:
    """Version string built like original category_struct NUMVERS from 55 header."""
    h = _normalize_55_header_bytes(header)
    try:
        if len(h) >= 6:
            major = int(h[4])
            minor = int(h[5])
            if 0 < major < 100 and 0 <= minor < 100:
                return f"{major:02d}.{minor:02d}"
    except Exception:
        pass
    return "06.43"


def _native_header_device(header: bytes) -> str:
    h = _normalize_55_header_bytes(header)
    try:
        v = device_no_from_header(h)
        return "" if v is None else str(v)
    except Exception:
        return ""


def _report_header_for_addr(db: PelengDB, addr: int) -> bytes:
    """Find the best session header for a report address.

    Prefer idx_catalog.header_hex because it is saved directly from the 55
    catalogue. raw_records.header_hex can be stale/broken if an older script saved
    a shifted header; using it first produced false meta such as device 10758 and
    version 17.11.
    """
    candidates: list[bytes] = []
    try:
        idx_row = db.conn.execute("SELECT header_hex FROM idx_catalog WHERE address=? ORDER BY id DESC LIMIT 1", (int(addr),)).fetchone()
        if idx_row and idx_row["header_hex"]:
            candidates.append(bytes.fromhex(str(idx_row["header_hex"])))
    except Exception:
        pass
    try:
        # If there is no exact idx row (old DB), any latest 55 catalogue header is
        # better than payload-derived report bytes.
        idx_row = db.conn.execute("SELECT header_hex FROM idx_catalog WHERE header_hex IS NOT NULL AND header_hex<>'' ORDER BY id DESC LIMIT 1").fetchone()
        if idx_row and idx_row["header_hex"]:
            candidates.append(bytes.fromhex(str(idx_row["header_hex"])))
    except Exception:
        pass
    try:
        raw_row = db.get_raw_by_addr(int(addr))
        if raw_row is not None:
            hx = str(raw_row["header_hex"] or "")
            if hx:
                candidates.append(bytes.fromhex(hx))
    except Exception:
        pass

    def meta_score(h: bytes) -> int:
        n = _normalize_55_header_bytes(h)
        if len(n) < 6:
            return -9999
        dev = safe_le16(n, 0, 0)
        maj, minor = n[4], n[5]
        sc = 0
        if 1 <= dev <= 9999:
            sc += 30
        if maj == 6 and minor in (42, 43):
            sc += 60
        elif 1 <= maj <= 9 and 0 <= minor <= 99:
            sc += 20
        return sc

    if candidates:
        candidates.sort(key=meta_score, reverse=True)
        return _normalize_55_header_bytes(candidates[0])
    return b""


def _apply_native_report_session_meta(db: PelengDB, addr: int, fields: dict[str, str], header: bytes | None = None) -> dict[str, str]:
    """Patch report meta that original DLL takes from EXE header16, not from payload."""
    h = header or _report_header_for_addr(db, addr)
    if h:
        fields = dict(fields)
        # Keep NUMVERS from payload (e.g. real 6.42); header/default may be 6.43.
        dev = _native_header_device(h)
        if dev:
            fields["NUMPRIB"] = dev
    # Original report date/time for clean live records is in payload+7:
    # [DD MM YY HH MM].  Keep this as a hard correction because generic
    # fallback may prefer older/false windows.
    try:
        raw_row = db.get_raw_by_addr(int(addr))
        raw = bytes(raw_row["raw"]) if raw_row else b""
        if raw:
            d, t = best_datetime(raw, (0x07,))
            if d:
                fields["DATEFORM"] = d
                fields["TIMEFORM"] = t
    except Exception:
        pass
    return fields


def _report_children_idx_rows(db: PelengDB, base: int) -> list[sqlite3.Row]:
    return list(db.conn.execute(
        """
        SELECT * FROM idx_catalog
        WHERE bucket='reports' AND address>=? AND address<?
        ORDER BY address
        """,
        (int(base), int(base) + 100),
    ))




# ---------------------------------------------------------------------------
# PostgreSQL export layer
# ---------------------------------------------------------------------------

PG_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "peleng_postgres_config.json")

APP_FIELDS_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "peleng_report_fields_config.json")


def _fields_default_config() -> dict[str, Any]:
    """User-editable report header fields and operator code directory.

    These are not transport/decode values.  They are user-facing labels used in
    report sheets and PostgreSQL export, exactly like the native report template
    fields: Предприятие, Подразделение, and operator name by code.
    """
    return {
        "enterprise": "ВЧДэ Россошь",
        "subdivision": "НК",
        "operators": {},
    }


def _fields_load_config() -> dict[str, Any]:
    cfg = _fields_default_config()
    try:
        if os.path.exists(APP_FIELDS_CONFIG_PATH):
            with open(APP_FIELDS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for key in ("enterprise", "subdivision"):
                    if key in data:
                        cfg[key] = str(data.get(key) or "")
                ops = data.get("operators")
                if isinstance(ops, dict):
                    cfg["operators"] = {str(k).strip(): str(v).strip() for k, v in ops.items() if str(k).strip()}
    except Exception:
        pass
    return cfg


def _fields_save_config(cfg: dict[str, Any]) -> None:
    clean = _fields_default_config()
    clean["enterprise"] = str(cfg.get("enterprise") or "").strip()
    clean["subdivision"] = str(cfg.get("subdivision") or "").strip()
    ops = cfg.get("operators") or {}
    clean["operators"] = {str(k).strip(): str(v).strip() for k, v in dict(ops).items() if str(k).strip()}
    with open(APP_FIELDS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)


def _report_enterprise() -> str:
    return str(_fields_load_config().get("enterprise") or "")


def _report_subdivision() -> str:
    return str(_fields_load_config().get("subdivision") or "")


def _normalize_operator_code(code: Any) -> str:
    s = str(code or "").strip()
    # Native reports often display code as two digits; preserve non-numeric codes.
    if s.isdigit() and len(s) < 2:
        s = s.zfill(2)
    return s


def _operator_name_for_code(code: Any, fallback: str = "") -> str:
    code_s = _normalize_operator_code(code)
    ops = _fields_load_config().get("operators") or {}
    name = str(ops.get(code_s) or "").strip()
    return name or str(fallback or "").strip()


def _apply_operator_directory_to_sqlite(db: Any) -> int:
    """Apply operator-code → operator-name mapping to all decoded SQLite rows."""
    ops = _fields_load_config().get("operators") or {}
    if not ops:
        return 0
    total = 0
    try:
        for table in ("reports", "protocols", "settings"):
            existing = {row[1] for row in db.conn.execute(f"PRAGMA table_info({table})")}
            if "KODOPERA" not in existing or "NAMEOPERA" not in existing:
                continue
            for code, name in ops.items():
                db.conn.execute(
                    f"UPDATE {table} SET NAMEOPERA=? WHERE TRIM(COALESCE(KODOPERA,'')) IN (?,?)",
                    (str(name), str(code), str(code).lstrip("0") or str(code)),
                )
                total += int(db.conn.total_changes)
        db.conn.commit()
    except Exception:
        pass
    return total


def _apply_operator_directory_to_addr(db: Any, addr: int) -> None:
    ops = _fields_load_config().get("operators") or {}
    if not ops:
        return
    kind = kind_for_addr(int(addr))
    table = "reports" if kind in ("report", "report_v2") else "protocols" if kind in ("protocol_short", "protocol_graph", "bscan") else "settings" if kind == "setting" else ""
    if not table:
        return
    try:
        row = db.conn.execute(f"SELECT KODOPERA FROM {table} WHERE address=?", (int(addr),)).fetchone()
        if not row:
            return
        code = _normalize_operator_code(row["KODOPERA"])
        name = str(ops.get(code) or ops.get(code.lstrip("0")) or "").strip()
        if name:
            db.conn.execute(f"UPDATE {table} SET NAMEOPERA=? WHERE address=?", (name, int(addr)))
            if not getattr(db, "bulk_depth", 0) > 0:
                db.conn.commit()
    except Exception:
        pass


class ReportFieldsSettingsDialog(tk.Toplevel):
    """Settings window for report header labels and operator code directory."""

    def __init__(self, master: tk.Misc, db: Optional[Any] = None, on_saved: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.db = db
        self.on_saved = on_saved
        self.title("Настройки отчётов")
        self.geometry("560x420")
        self.minsize(520, 380)
        self.cfg = _fields_load_config()
        self.enterprise_var = tk.StringVar(value=str(self.cfg.get("enterprise") or ""))
        self.subdivision_var = tk.StringVar(value=str(self.cfg.get("subdivision") or ""))
        self.op_code_var = tk.StringVar(value="")
        self.op_name_var = tk.StringVar(value="")
        self._build()
        self._refresh_operator_list()
        try:
            self.transient(master)
            self.grab_set()
        except Exception:
            pass

    def _build(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(5, weight=1)

        ttk.Label(root, text="Эти значения сразу применяются к отчётам, окну двойного клика и PostgreSQL-выгрузке.").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(root, text="Предприятие").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(root, textvariable=self.enterprise_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(root, text="Подразделение").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(root, textvariable=self.subdivision_var).grid(row=2, column=1, columnspan=2, sticky="ew", pady=3)

        ttk.Separator(root).grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(root, text="Операторы по шифру").grid(row=4, column=0, columnspan=3, sticky="w")
        self.op_list = tk.Listbox(root, height=8)
        self.op_list.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(4, 6))
        self.op_list.bind("<<ListboxSelect>>", self._on_select_operator)

        ttk.Label(root, text="Шифр").grid(row=6, column=0, sticky="w")
        ttk.Entry(root, textvariable=self.op_code_var, width=10).grid(row=6, column=1, sticky="w")
        ttk.Label(root, text="ФИО").grid(row=7, column=0, sticky="w")
        ttk.Entry(root, textvariable=self.op_name_var).grid(row=7, column=1, columnspan=2, sticky="ew")

        btns = ttk.Frame(root)
        btns.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Добавить / заменить оператора", command=self._add_operator).pack(side=tk.LEFT)
        ttk.Button(btns, text="Удалить оператора", command=self._delete_operator).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Сохранить и применить", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side=tk.RIGHT, padx=6)

    def _operators(self) -> dict[str, str]:
        ops = self.cfg.setdefault("operators", {})
        if not isinstance(ops, dict):
            self.cfg["operators"] = {}
        return self.cfg["operators"]

    def _refresh_operator_list(self) -> None:
        self.op_list.delete(0, tk.END)
        for code, name in sorted(self._operators().items()):
            self.op_list.insert(tk.END, f"{code} — {name}")

    def _on_select_operator(self, _event=None) -> None:
        sel = self.op_list.curselection()
        if not sel:
            return
        item = self.op_list.get(sel[0])
        code = item.split("—", 1)[0].strip()
        name = self._operators().get(code, "")
        self.op_code_var.set(code)
        self.op_name_var.set(name)

    def _add_operator(self) -> None:
        code = _normalize_operator_code(self.op_code_var.get())
        name = str(self.op_name_var.get() or "").strip()
        if not code:
            messagebox.showwarning("Оператор", "Введите шифр оператора", parent=self)
            return
        if not name:
            messagebox.showwarning("Оператор", "Введите ФИО оператора", parent=self)
            return
        self._operators()[code] = name
        self._refresh_operator_list()

    def _delete_operator(self) -> None:
        code = _normalize_operator_code(self.op_code_var.get())
        if code in self._operators():
            del self._operators()[code]
            self._refresh_operator_list()
            self.op_code_var.set("")
            self.op_name_var.set("")

    def _save(self) -> None:
        self.cfg["enterprise"] = str(self.enterprise_var.get() or "").strip()
        self.cfg["subdivision"] = str(self.subdivision_var.get() or "").strip()
        _fields_save_config(self.cfg)
        changed = 0
        if self.db is not None:
            changed = _apply_operator_directory_to_sqlite(self.db)
        if self.on_saved:
            try:
                self.on_saved()
            except Exception:
                pass
        messagebox.showinfo("Настройки отчётов", f"Сохранено. Операторы применены к существующим строкам.", parent=self)
        self.destroy()



def _pg_default_config() -> dict[str, Any]:
    return {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "peleng",
        "user": "postgres",
        "password": "",
        "sslmode": "prefer",
        "schema": "public",
    }


def _pg_load_config() -> dict[str, Any]:
    cfg = _pg_default_config()
    try:
        if os.path.exists(PG_CONFIG_PATH):
            with open(PG_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in cfg})
    except Exception:
        pass
    try:
        cfg["port"] = int(cfg.get("port") or 5432)
    except Exception:
        cfg["port"] = 5432
    return cfg


def _pg_save_config(cfg: dict[str, Any]) -> None:
    clean = _pg_default_config()
    clean.update({k: cfg.get(k, clean[k]) for k in clean})
    clean["port"] = int(clean.get("port") or 5432)
    with open(PG_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)


def _pg_ident(name: str) -> str:
    name = str(name or "public").strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise ValueError("Имя схемы PostgreSQL должно содержать только латиницу, цифры и подчёркивание, начинаться с буквы/подчёркивания")
    return '"' + name.replace('"', '""') + '"'


def _pg_table(schema: str, table: str) -> str:
    return f"{_pg_ident(schema)}.{_pg_ident(table)}"


def _pg_connect(cfg: dict[str, Any]):
    """Return (conn, driver_name). Supports psycopg v3 and psycopg2."""
    params = dict(
        host=str(cfg.get("host") or "127.0.0.1"),
        port=int(cfg.get("port") or 5432),
        dbname=str(cfg.get("dbname") or "peleng"),
        user=str(cfg.get("user") or "postgres"),
        password=str(cfg.get("password") or ""),
    )
    sslmode = str(cfg.get("sslmode") or "").strip()
    if sslmode:
        params["sslmode"] = sslmode
    try:
        import psycopg  # type: ignore
        return psycopg.connect(**params), "psycopg"
    except ImportError:
        try:
            import psycopg2  # type: ignore
            return psycopg2.connect(**params), "psycopg2"
        except ImportError as exc:
            raise RuntimeError(
                "Не установлен PostgreSQL-драйвер. Установите один из вариантов:\n"
                "  python -m pip install psycopg[binary]\n"
                "или\n"
                "  python -m pip install psycopg2-binary"
            ) from exc



def _v25_apply_report_fields_to_decoded_sqlite(sqlite_path: str | None = None) -> None:
    """Apply current report-field settings to the compact decoded SQLite.

    Operators edit enterprise/subdivision/operator names in the report-fields
    dialog.  The UI reads these values live, but PostgreSQL export-all reads the
    compact decoded DB, so mirror those user fields into reports/protocols right
    before export and immediately after saving the dialog.
    """
    try:
        cfg = _v23_load_ini()
    except Exception:
        cfg = {}
    enterprise = str(cfg.get("enterprise") or "")
    subdivision = str(cfg.get("subdivision") or "")
    operators = dict(cfg.get("operators") or {})
    path = _portable_resolve_data_path(sqlite_path or _v20_user_db_path(None), "peleng_vagon643_decoded.sqlite3")
    if not os.path.exists(path):
        return
    conn = _v25_clean_connect_compact(None) if sqlite_path is None else sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        with conn:
            for table in ("reports", "protocols"):
                cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
                if not cols:
                    continue
                assigns: list[str] = []
                params: list[Any] = []
                if "enterprise" in cols:
                    assigns.append('"enterprise"=?')
                    params.append(enterprise)
                if "subdivision" in cols:
                    assigns.append('"subdivision"=?')
                    params.append(subdivision)
                if assigns:
                    conn.execute(f'UPDATE "{table}" SET {", ".join(assigns)}', params)
                if "operator_code" in cols and "operator_name" in cols and operators:
                    for code, name in operators.items():
                        code_s = _normalize_operator_code(code) if "_normalize_operator_code" in globals() else str(code).strip()
                        if not code_s:
                            continue
                        conn.execute(
                            f"UPDATE \"{table}\" SET \"operator_name\"=? WHERE TRIM(COALESCE(\"operator_code\", '')) IN (?,?)",
                            (str(name), code_s, code_s.lstrip("0") or code_s),
                        )
    finally:
        conn.close()


class PostgresExporter:
    """Exporter for decoded columns only, user-facing schema.

    Scope:
      * selected report/protocol export for interactive actions;
      * full decoded SQLite export for reports, protocols and settings only.

    No raw bytes, no BYTEA, no JSONB, and no runtime basket export.
    Report export intentionally does NOT include transport/internal columns such
    as address, report_base, row_no, NUMBER, or NUMKOD.
    """

    REPORT_TABLE = 'peleng_reports_control_decoded'
    PROTOCOL_TABLE = 'peleng_protocols_decoded'
    LOG_TABLE = 'peleng_export_log'
    DECODED_MIRROR_TABLES = {
        'reports': 'reports',
        'protocols': 'protocols',
        'settings': 'settings',
    }

    def __init__(self, cfg: Optional[dict[str, Any]] = None):
        self.cfg = cfg or _pg_load_config()
        self.schema = str(self.cfg.get("schema") or "public").strip() or "public"

    def connect(self):
        return _pg_connect(self.cfg)[0]

    @staticmethod
    def _typevar_text(v: Any) -> str:
        """Export typevar as user-facing text, e.g. 834 -> колесо."""
        try:
            tv = int(_short_typevar(v))
        except Exception:
            return str(v or "").strip()
        info = typevar_info_643(tv)
        obj = str(info.get("object") or "").strip()
        detail = str(info.get("detail") or "").strip()
        if tv // 100 == 8:
            return obj or "колесо"
        if tv // 100 == 7:
            return obj or "ось РУ1Ш"
        return obj or detail or str(tv)

    def ensure_schema(self, conn) -> None:
        schema_q = _pg_ident(self.schema)
        ddl = f"""
        CREATE SCHEMA IF NOT EXISTS {schema_q};

        CREATE TABLE IF NOT EXISTS {_pg_table(self.schema, self.LOG_TABLE)} (
            id BIGSERIAL PRIMARY KEY,
            exported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            action TEXT NOT NULL,
            object_type TEXT,
            ok BOOLEAN NOT NULL DEFAULT TRUE,
            message TEXT,
            rows_count INTEGER,
            elapsed_sec DOUBLE PRECISION
        );

        CREATE TABLE IF NOT EXISTS {_pg_table(self.schema, self.REPORT_TABLE)} (
            report_no TEXT,
            line_no INTEGER,
            report_title TEXT,
            device_no TEXT,
            software_version TEXT,
            enterprise TEXT,
            subdivision TEXT,
            operator_code TEXT,
            operator_name TEXT,
            ntd TEXT,
            setting_no TEXT,
            control_date TEXT,
            control_time TEXT,
            typevar TEXT,
            object_type TEXT,
            object_number TEXT,
            smelting TEXT,
            factory TEXT,
            production_year TEXT,
            side TEXT,
            neck TEXT,
            rim TEXT,
            wheel_turning TEXT,
            crest TEXT,
            defects_count TEXT,
            protocol TEXT,
            exported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT peleng_reports_control_decoded_uq
                UNIQUE(report_no, line_no, control_date, control_time, object_number)
        );

        CREATE INDEX IF NOT EXISTS peleng_reports_control_decoded_report_idx
            ON {_pg_table(self.schema, self.REPORT_TABLE)} (report_no, line_no);

        CREATE TABLE IF NOT EXISTS {_pg_table(self.schema, self.PROTOCOL_TABLE)} (
            address INTEGER PRIMARY KEY,
            typezap TEXT,
            dateform TEXT,
            timeform TEXT,
            kodopera TEXT,
            nameopera TEXT,
            numvers TEXT,
            numprib TEXT,
            typevar TEXT,
            numobj TEXT,
            smelting TEXT,
            indmaker TEXT,
            maketime TEXT,
            defekt TEXT,
            codedef TEXT,
            setting_no TEXT,
            setting_addr TEXT,
            graph_addr TEXT,
            special TEXT,
            exported_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()

    @staticmethod
    def _s(v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @staticmethod
    def _row_get(row: sqlite3.Row, key: str, default: str = "") -> str:
        try:
            return PostgresExporter._s(row[key])
        except Exception:
            return default

    def _log(self, conn, action: str, object_type: str = "", ok: bool = True, message: str = "", rows_count: int = 0, elapsed_sec: float = 0.0) -> None:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {_pg_table(self.schema, self.LOG_TABLE)}(action,object_type,ok,message,rows_count,elapsed_sec) VALUES(%s,%s,%s,%s,%s,%s)",
                (action, object_type, ok, message, rows_count, float(elapsed_sec or 0.0)),
            )

    def _report_no_for_base(self, base: int) -> str:
        try:
            return str((int(base) % 10000) // 100)
        except Exception:
            return ""

    def export_report(self, conn, db: PelengDB, row: sqlite3.Row, line_no: Optional[int] = None, report_base: Optional[int] = None) -> None:
        addr = int(row["address"])
        report_base = int(report_base if report_base is not None else native_report_container_base(addr))
        try:
            detail = _native_report_detail_values(db, row)
        except Exception as exc:
            detail = {}
            self._log(conn, "report_detail_decode", "report", False, str(exc), 0, 0.0)

        report_no = self._report_no_for_base(report_base)
        device_no = self._row_get(row, "NUMPRIB")
        software_version = _v25_version_for_runtime_row(db, row, addr)
        operator_code = self._row_get(row, "KODOPERA")
        operator_name = self._row_get(row, "NAMEOPERA")
        typevar_text = self._typevar_text(self._row_get(row, "TYPEVAR") or detail.get("obj_type"))
        object_type = self._s(detail.get("obj_type")) or typevar_text
        setting_no = self._s(detail.get("setting_no"))
        try:
            tv = int(_short_typevar(self._row_get(row, "TYPEVAR")))
            ntd = typevar_info_643(tv).get("ntd") or ""
        except Exception:
            ntd = ""
        if not ntd:
            ntd = "СТО РЖД 1.11.002-2008 (ТИ 07.73-2009)"

        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_pg_table(self.schema, self.REPORT_TABLE)} (
                    report_no, line_no, report_title, device_no, software_version,
                    enterprise, subdivision, operator_code, operator_name, ntd, setting_no,
                    control_date, control_time, typevar, object_type, object_number, smelting,
                    factory, production_year, side, neck, rim, wheel_turning, crest,
                    defects_count, protocol, exported_at
                ) VALUES (
                    %s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,
                    %s,%s,now()
                )
                ON CONFLICT(report_no, line_no, control_date, control_time, object_number) DO UPDATE SET
                    report_title=excluded.report_title,
                    device_no=excluded.device_no,
                    software_version=excluded.software_version,
                    enterprise=excluded.enterprise,
                    subdivision=excluded.subdivision,
                    operator_code=excluded.operator_code,
                    operator_name=excluded.operator_name,
                    ntd=excluded.ntd,
                    setting_no=excluded.setting_no,
                    typevar=excluded.typevar,
                    object_type=excluded.object_type,
                    smelting=excluded.smelting,
                    factory=excluded.factory,
                    production_year=excluded.production_year,
                    side=excluded.side,
                    neck=excluded.neck,
                    rim=excluded.rim,
                    wheel_turning=excluded.wheel_turning,
                    crest=excluded.crest,
                    defects_count=excluded.defects_count,
                    protocol=excluded.protocol,
                    exported_at=now()
                """,
                (
                    report_no, int(line_no or 0), f"ОТЧЕТ № {report_no}", device_no, software_version,
                    _report_enterprise(), _report_subdivision(), operator_code, _operator_name_for_code(operator_code, operator_name), ntd, setting_no,
                    _native_report_display_date(self._s(detail.get("date"))), self._s(detail.get("time")),
                    typevar_text, object_type, self._s(detail.get("numobj")), self._s(detail.get("smelting")),
                    self._s(detail.get("factory")), self._s(detail.get("year")), self._s(detail.get("side")),
                    self._s(detail.get("neck")), self._s(detail.get("rim")), self._s(detail.get("wheel_turn")),
                    self._s(detail.get("crest")), self._s(detail.get("defects")), self._row_get(row, "PROTOCOL"),
                ),
            )

    def export_protocol(self, conn, db: PelengDB, row: sqlite3.Row) -> None:
        addr = int(row["address"])
        typevar_text = self._typevar_text(self._row_get(row, "TYPEVAR"))
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_pg_table(self.schema, self.PROTOCOL_TABLE)} (
                    address, typezap, dateform, timeform, kodopera, nameopera,
                    numvers, numprib, typevar, numobj, smelting, indmaker,
                    maketime, defekt, codedef, setting_no, setting_addr,
                    graph_addr, special, exported_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,
                    %s,%s,now()
                )
                ON CONFLICT(address) DO UPDATE SET
                    typezap=excluded.typezap,
                    dateform=excluded.dateform,
                    timeform=excluded.timeform,
                    kodopera=excluded.kodopera,
                    nameopera=excluded.nameopera,
                    numvers=excluded.numvers,
                    numprib=excluded.numprib,
                    typevar=excluded.typevar,
                    numobj=excluded.numobj,
                    smelting=excluded.smelting,
                    indmaker=excluded.indmaker,
                    maketime=excluded.maketime,
                    defekt=excluded.defekt,
                    codedef=excluded.codedef,
                    setting_no=excluded.setting_no,
                    setting_addr=excluded.setting_addr,
                    graph_addr=excluded.graph_addr,
                    special=excluded.special,
                    exported_at=now()
                """,
                (
                    addr,
                    self._row_get(row, "TYPEZAP"), self._row_get(row, "DATEFORM"),
                    self._row_get(row, "TIMEFORM"), self._row_get(row, "KODOPERA"),
                    _operator_name_for_code(self._row_get(row, "KODOPERA"), self._row_get(row, "NAMEOPERA")), self._row_get(row, "NUMVERS"),
                    self._row_get(row, "NUMPRIB"), typevar_text,
                    self._row_get(row, "NUMOBJ"), self._row_get(row, "SMELTING"),
                    self._row_get(row, "INDMAKER"), self._row_get(row, "MAKETIME"),
                    self._row_get(row, "DEFEKT"), self._row_get(row, "CODEDEF"),
                    self._row_get(row, "SETTING_NO"), self._row_get(row, "SETTING_ADDR"),
                    self._row_get(row, "GRAPH_ADDR"), self._row_get(row, "SPECIAL"),
                ),
            )

    def export_address(self, db: PelengDB, addr: int) -> tuple[int, str]:
        started = time.perf_counter()
        addr = int(addr)
        with self.connect() as conn:
            self.ensure_schema(conn)
            k = kind_for_addr(addr)
            count = 0
            if k in ("report", "report_v2"):
                row = db.row_by_addr("reports", addr)
                if row is None:
                    raise RuntimeError(f"Отчёт {addr} ещё не дешифрован")
                self.export_report(conn, db, row, line_no=1, report_base=native_report_container_base(addr))
                count = 1
                obj = "report"
            elif k in ("protocol_short", "protocol_graph", "bscan"):
                row = db.row_by_addr("protocols", addr)
                if row is None:
                    raise RuntimeError(f"Протокол {addr} ещё не дешифрован")
                self.export_protocol(conn, db, row)
                count = 1
                obj = "protocol"
            else:
                raise RuntimeError("В этой версии PostgreSQL-выгрузки поддержаны только отчёты и протоколы")
            self._log(conn, "export_address", obj, True, f"exported {count}", count, time.perf_counter() - started)
            conn.commit()
        return count, f"Выгружено: {count} ({addr})"

    def export_report_container(self, db: PelengDB, base: int) -> tuple[int, str]:
        started = time.perf_counter()
        base = int(base)
        rows = list(db.conn.execute("SELECT * FROM reports WHERE address>=? AND address<? ORDER BY address", (base, base + 100)))
        if not rows:
            raise RuntimeError(f"Контейнер {base} ещё не дешифрован")
        with self.connect() as conn:
            self.ensure_schema(conn)
            for i, row in enumerate(rows, 1):
                self.export_report(conn, db, row, line_no=i, report_base=base)
            self._log(conn, "export_report_container", "report_container", True, f"exported {len(rows)} rows", len(rows), time.perf_counter() - started)
            conn.commit()
        return len(rows), f"Выгружен контейнер {base}: {len(rows)} строк"

    def export_all_decoded(self, db: PelengDB) -> tuple[int, str]:
        started = time.perf_counter()
        # Export report containers in native grouping order so line_no matches the double-click sheet.
        report_rows = db.rows("reports")
        bases: dict[int, list[sqlite3.Row]] = {}
        for r in report_rows:
            bases.setdefault(native_report_container_base(int(r["address"])), []).append(r)
        protocols = db.rows("protocols")
        with self.connect() as conn:
            self.ensure_schema(conn)
            n = 0
            for base in sorted(bases):
                for i, row in enumerate(sorted(bases[base], key=lambda rr: int(rr["address"])), 1):
                    self.export_report(conn, db, row, line_no=i, report_base=base)
                    n += 1
            for row in protocols:
                self.export_protocol(conn, db, row)
                n += 1
            msg = f"exported {n} decoded rows: reports {len(report_rows)}, protocols {len(protocols)}"
            self._log(conn, "export_all_decoded", "reports_protocols", True, msg, n, time.perf_counter() - started)
            conn.commit()
        return n, f"Выгружено всего: {n} (отчёты {len(report_rows)}, протоколы {len(protocols)}). Настройки и RAW не выгружались."

    def export_decoded_database(self, sqlite_path: str) -> tuple[int, str]:
        """Export only the compact decoded SQLite tables: reports/protocols/settings.

        The PostgreSQL "Выгрузить всё" action must not read or mirror runtime
        basket/raw tables.  It rebuilds three PostgreSQL mirror tables from
        peleng_vagon643_decoded.sqlite3 and nothing else.
        """
        path = _portable_resolve_data_path(sqlite_path, "peleng_vagon643_decoded.sqlite3")
        if not os.path.exists(path):
            raise RuntimeError(f"Decoded SQLite не найден: {path}")
        _v25_apply_report_fields_to_decoded_sqlite(path)

        decoded: dict[str, tuple[list[str], list[sqlite3.Row]]] = {}
        src = sqlite3.connect(path)
        src.row_factory = sqlite3.Row
        try:
            for table in ("reports", "protocols", "settings"):
                exists = src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                cols = [name for name, _typ in V25_CLEAN_SCHEMAS[table]]
                if not exists:
                    decoded[table] = (cols, [])
                    continue
                col_sql = ",".join(f'"{c}"' for c in cols)
                rows = list(src.execute(f'SELECT {col_sql} FROM "{table}" ORDER BY rowid'))
                decoded[table] = (cols, rows)
        finally:
            src.close()

        with self.connect() as conn:
            schema_q = _pg_ident(self.schema)
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_q}")
                for table in ("reports", "protocols", "settings"):
                    cols, rows = decoded[table]
                    target = self.DECODED_MIRROR_TABLES[table]
                    full_name = _pg_table(self.schema, target)
                    col_defs = ", ".join(f"{_pg_ident(c)} TEXT" for c in cols)
                    cur.execute(f"DROP TABLE IF EXISTS {full_name}")
                    cur.execute(f"CREATE TABLE {full_name} ({col_defs})")
                    if rows:
                        col_names = ", ".join(_pg_ident(c) for c in cols)
                        placeholders = ", ".join(["%s"] * len(cols))
                        sql = f"INSERT INTO {full_name} ({col_names}) VALUES ({placeholders})"
                        for row in rows:
                            cur.execute(sql, tuple(self._row_get(row, c) for c in cols))
            conn.commit()

        counts = {table: len(rows) for table, (_cols, rows) in decoded.items()}
        total = sum(counts.values())
        return total, (
            "Выгружено из peleng_vagon643_decoded.sqlite3: "
            f"отчёты {counts['reports']}, протоколы {counts['protocols']}, настройки {counts['settings']}. "
            "Runtime basket/RAW не читались."
        )


class PostgresSettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.title("Настройки PostgreSQL")
        self.geometry("470x320")
        self.resizable(False, False)
        self.cfg = _pg_load_config()
        self.vars: dict[str, tk.StringVar] = {}
        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        fields = [
            ("host", "Host"),
            ("port", "Port"),
            ("dbname", "Database"),
            ("user", "User"),
            ("password", "Password"),
            ("sslmode", "SSL mode"),
            ("schema", "Schema"),
        ]
        for r, (key, label) in enumerate(fields):
            ttk.Label(body, text=label, width=14).grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=str(self.cfg.get(key, "")))
            self.vars[key] = var
            show = "*" if key == "password" else ""
            ttk.Entry(body, textvariable=var, width=36, show=show).grid(row=r, column=1, sticky="ew", pady=4)
        body.columnconfigure(1, weight=1)
        btns = ttk.Frame(body)
        btns.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(btns, text="Проверить", command=self.test_connection).pack(side=tk.LEFT)
        ttk.Button(btns, text="Сохранить", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def _collect(self) -> dict[str, Any]:
        cfg = {k: v.get() for k, v in self.vars.items()}
        try:
            cfg["port"] = int(cfg.get("port") or 5432)
        except Exception:
            cfg["port"] = 5432
        return cfg

    def test_connection(self) -> None:
        cfg = self._collect()
        try:
            exporter = PostgresExporter(cfg)
            with exporter.connect() as conn:
                exporter.ensure_schema(conn)
            messagebox.showinfo("PostgreSQL", "Подключение успешно. Схема/таблицы готовы.", parent=self)
        except Exception as exc:
            messagebox.showerror("PostgreSQL", f"Ошибка подключения:\n{exc}", parent=self)

    def save(self) -> None:
        try:
            cfg = self._collect()
            _pg_ident(str(cfg.get("schema") or "public"))
            _pg_save_config(cfg)
            messagebox.showinfo("PostgreSQL", f"Настройки сохранены:\n{PG_CONFIG_PATH}", parent=self)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("PostgreSQL", str(exc), parent=self)


def _pg_exporter() -> PostgresExporter:
    return PostgresExporter(_pg_load_config())


def _ui_pg_open_settings(self) -> None:
    PostgresSettingsDialog(self)


def _ui_pg_export_selected(self) -> None:
    try:
        addr = self.selected_addr()
        if addr is None:
            messagebox.showinfo("PostgreSQL", "Выберите строку для выгрузки.")
            return
        base = None
        try:
            base = self.selected_base()
        except Exception:
            base = None
        exporter = _pg_exporter()
        if base is not None and kind_for_addr(int(addr)) in ("report", "report_v2"):
            _n, msg = exporter.export_report_container(self.db, int(base))
        else:
            _n, msg = exporter.export_address(self.db, int(addr))
        messagebox.showinfo("PostgreSQL", msg)
    except Exception as exc:
        messagebox.showerror("PostgreSQL", f"Ошибка выгрузки:\n{exc}")


def _ui_pg_export_all(self) -> None:
    try:
        exporter = _pg_exporter()
        _n, msg = exporter.export_decoded_database(_v20_user_db_path(None))
        messagebox.showinfo("PostgreSQL", msg)
    except Exception as exc:
        messagebox.showerror("PostgreSQL", f"Ошибка выгрузки:\n{exc}")


def _report_sheet_export_to_pg(self) -> None:
    try:
        exporter = _pg_exporter()
        _n, msg = exporter.export_report_container(self.db, int(self.group_base))
        messagebox.showinfo("PostgreSQL", msg, parent=self)
    except Exception as exc:
        messagebox.showerror("PostgreSQL", f"Ошибка выгрузки:\n{exc}", parent=self)



def _native_report_display_date(date_s: str) -> str:
    """Native report sheet shows short dates like DD.MM.YY.

    Do not slice ``date[-8:]``: for ``08.04.2026`` that becomes
    ``.04.2026`` and loses the day.  Convert explicitly.
    """
    s = str(date_s or "").strip()
    if len(s) == 10 and s[2] == "." and s[5] == ".":
        return f"{s[0:2]}.{s[3:5]}.{s[8:10]}"
    return s

class NativeReportSheet(tk.Toplevel):
    """Report view styled after original PelengPC/zapis2 report sheet."""

    def __init__(self, master: tk.Misc, db: PelengDB, selected_addr: int):
        super().__init__(master)
        self.db = db
        self.selected_addr = int(selected_addr)
        self.group_base = native_report_container_base(self.selected_addr)
        self.title("Отчет о контроле")
        self.geometry("1180x780")
        self.minsize(980, 620)
        self.configure(bg="#efefef")
        self._build()

    def _rows_for_group(self) -> list[sqlite3.Row]:
        rows = list(self.db.conn.execute(
            "SELECT * FROM reports WHERE address>=? AND address<? ORDER BY address",
            (self.group_base, self.group_base + 100),
        ))
        if not rows:
            row = self.db.row_by_addr("reports", self.selected_addr)
            rows = [row] if row else []
        return rows

    def _build(self) -> None:
        top_menu = ttk.Frame(self)
        top_menu.pack(fill=tk.X)
        for t in ("Печать", "Сохранить", "Настройка"):
            ttk.Button(top_menu, text=t).pack(side=tk.LEFT, padx=(4, 2), pady=3)
        ttk.Button(top_menu, text="В PostgreSQL", command=self.export_to_postgres).pack(side=tk.LEFT, padx=(12, 2), pady=3)

        outer = tk.Frame(self, bg="#d8d8d8")
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))
        canvas = tk.Canvas(outer, bg="#d8d8d8", highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        hsb = ttk.Scrollbar(outer, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        page = tk.Frame(canvas, bg="white", bd=1, relief=tk.SOLID)
        canvas.create_window((20, 20), window=page, anchor="nw")
        page.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        rows = self._rows_for_group()
        first = rows[0] if rows else None
        first_vals = _native_report_detail_values(self.db, first) if first else {}
        device = str(first["NUMPRIB"] if first and "NUMPRIB" in first.keys() else "")
        version = _v25_version_for_runtime_row(self.db, first, int(first["address"])) if first and "address" in first.keys() else "06.43"
        ntd = "СТО РЖД 1.11.002-2008 (ТИ 07.73-2009)"
        try:
            tv = int(_short_typevar(first["TYPEVAR"])) if first else 0
            info = typevar_info_643(tv)
            ntd = info.get("ntd") or ntd
        except Exception:
            pass

        tk.Label(page, text=f"ОТЧЕТ № {self.group_base % 10000 // 100 if self.group_base else self.selected_addr % 10000}", bg="white", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 0))
        tk.Label(page, text=f"о контроле дефектоскопом УД2-102 № {device or '----'}, Версия {version or '6.43'}", bg="white", font=("Arial", 9)).grid(row=1, column=0, sticky="w", padx=18)

        info_frame = tk.Frame(page, bg="white")
        info_frame.grid(row=2, column=0, sticky="ew", padx=18, pady=(16, 12))
        operator_code = str(first["KODOPERA"] if first else "")
        operator_name = _operator_name_for_code(operator_code)
        left = [
            ("Предприятие", _report_enterprise()),
            ("Подразделение", _report_subdivision()),
            ("Оператор: шифр", operator_code),
            ("Фамилия", operator_name),
            ("НТД на контроль", ntd),
            ("Номер настройки", str(first_vals.get("setting_no", ""))),
        ]
        for r, (k, v) in enumerate(left):
            tk.Label(info_frame, text=k, bg="white", font=("Arial", 9), anchor="w", width=18).grid(row=r, column=0, sticky="w")
            tk.Label(info_frame, text=v, bg="white", font=("Arial", 11, "bold" if r in (0, 1, 3, 4) else "normal"), anchor="w", width=52).grid(row=r, column=1, sticky="w")

        cols = ["№", "Дата", "Объект: тип", "Номер объекта", "Плавка", "З-д", "Год", "Стор", "шейка", "обод", "обт. колес", "нал. гребня", "к-во деф"]
        table = tk.Frame(page, bg="white")
        table.grid(row=3, column=0, sticky="nw", padx=18, pady=(6, 18))
        widths = [4, 14, 18, 14, 9, 7, 6, 7, 13, 12, 11, 11, 8]
        for c, title in enumerate(cols):
            tk.Label(table, text=title, bg="#efefef", bd=1, relief=tk.SOLID, font=("Arial", 8, "bold"), width=widths[c], anchor="center").grid(row=0, column=c, sticky="nsew")
        for i, row in enumerate(rows, 1):
            vals = _native_report_detail_values(self.db, row)
            line = [
                str(i), _native_report_display_date(vals["date"]), vals["obj_type"], vals["numobj"], vals["smelting"], vals["factory"], vals["year"],
                vals["side"], vals["neck"], vals["rim"], vals["wheel_turn"], vals["crest"], vals["defects"],
            ]
            for c, val in enumerate(line):
                tk.Label(table, text=val, bg="white", bd=1, relief=tk.SOLID, font=("Arial", 8), width=widths[c], anchor="w" if c in (2, 8, 9, 10, 11) else "center").grid(row=i, column=c, sticky="nsew")

        tk.Label(page, text="Подпись:", bg="white", font=("Arial", 9)).grid(row=4, column=0, pady=(28, 30))



class NativeLikeApp(SimpleUserApp):
    """PelengPC-like main UI base class restored for header-safe build."""

    VIEW_TO_MODE = {
        "Отчеты контроля": "reports",
        "Протоколы А-развертки": "protocols",
        "Настройки": "settings",
        "Все записи": "all",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title("PelengPC ver.1.2")
        try:
            self.geometry("1280x760")
            self.minsize(1050, 620)
        except Exception:
            pass

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=(6, 4, 6, 6))
        root.pack(fill=tk.BOTH, expand=True)
        root.rowconfigure(3, weight=1)
        root.columnconfigure(0, weight=1)

        # Native-like top menu. PostgreSQL and report-field settings live under "Таблица",
        # while the toolbar is intentionally kept simple for operators.
        menuline = tk.Frame(root, bg="#efefef")
        menuline.grid(row=0, column=0, sticky="ew")

        data_btn = tk.Menubutton(menuline, text="Данные", bg="#efefef", font=("Tahoma", 10), padx=12, pady=4, relief=tk.FLAT)
        data_menu = tk.Menu(data_btn, tearoff=0)
        data_menu.add_command(label="Обновить COM-порты", command=self.refresh_ports)
        data_menu.add_command(label="Получить отчёты", command=self.start_get_data)
        data_btn.configure(menu=data_menu)
        data_btn.pack(side=tk.LEFT)

        table_btn = tk.Menubutton(menuline, text="Таблица", bg="#efefef", font=("Tahoma", 10), padx=12, pady=4, relief=tk.FLAT)
        table_menu = tk.Menu(table_btn, tearoff=0)
        table_menu.add_command(label="Поля отчёта...", command=self.open_report_fields_settings)
        table_menu.add_separator()
        table_menu.add_command(label="PostgreSQL: настройки...", command=self.open_pg_settings)
        table_menu.add_command(label="PostgreSQL: выгрузить всё", command=self.export_all_to_postgres)
        table_btn.configure(menu=table_menu)
        table_btn.pack(side=tk.LEFT)

        for item in ("Вид", "Настройка", "Помощь"):
            tk.Label(menuline, text=item, bg="#efefef", font=("Tahoma", 10), padx=12, pady=4).pack(side=tk.LEFT)

        # Minimal operator toolbar: COM selection + one receive button.
        toolbar = tk.Frame(root, bg="#efefef", bd=1, relief=tk.GROOVE)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        tk.Label(toolbar, text="COM", bg="#efefef", font=("Tahoma", 9)).pack(side=tk.LEFT, padx=(6, 4), pady=4)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(toolbar, textvariable=self.port_var, width=11, state="readonly")
        self.port_combo.pack(side=tk.LEFT, padx=(0, 10), pady=4)
        self.btn_get = ttk.Button(toolbar, text="Получить отчёт", command=self.start_get_data)
        self.btn_get.pack(side=tk.LEFT, padx=3, pady=3)

        # Hidden technical defaults.
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        self.parity_var = tk.StringVar(value="E")
        self.clear_idx_var = tk.BooleanVar(value=True)
        self.mode_var = tk.StringVar(value="reports")

        selector = ttk.Frame(root)
        selector.grid(row=2, column=0, sticky="ew", pady=(2, 4))
        ttk.Label(selector, text="Вид записи", font=("Tahoma", 10)).pack(side=tk.LEFT, padx=(6, 8))
        self.view_var = tk.StringVar(value="Отчеты контроля")
        self.view_combo = ttk.Combobox(selector, textvariable=self.view_var, width=32, state="readonly", values=list(self.VIEW_TO_MODE))
        self.view_combo.pack(side=tk.LEFT)
        self.view_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_view_changed())
        ttk.Label(selector, text="   ").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="")
        ttk.Label(selector, textvariable=self.status_var, style="Hint.TLabel").pack(side=tk.LEFT, padx=(12, 0))
        self.progress_var = tk.StringVar(value="")
        ttk.Label(selector, textvariable=self.progress_var, style="Hint.TLabel").pack(side=tk.RIGHT, padx=(8, 6))

        frame = ttk.Frame(root)
        frame.grid(row=3, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.main_tree = ttk.Treeview(frame, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.main_tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.main_tree.xview)
        self.main_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.main_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.main_tree.bind("<Double-1>", lambda _e: self.open_selected_detail())
        self.trees = {"main": self.main_tree}
        self.tabs = None
        self.btn_55 = self.btn_get
        self.btn_42 = self.btn_get
        self.log_text = None
        self._configure_columns()

    def _on_view_changed(self) -> None:
        self.mode_var.set(self.VIEW_TO_MODE.get(self.view_var.get(), "reports"))
        self._configure_columns()
        self.reload_idx_tables()

    def _column_defs(self) -> list[tuple[str, str, int]]:
        mode = self.mode_var.get()
        if mode == "protocols":
            return _NATIVE_PROTOCOL_COLS
        if mode == "settings":
            return _NATIVE_SETTING_COLS
        return _NATIVE_REPORT_COLS

    def _configure_columns(self) -> None:
        defs = self._column_defs()
        cols = [c for c, _h, _w in defs]
        self.main_tree.configure(columns=cols)
        for c, h, w in defs:
            self.main_tree.heading(c, text=h)
            self.main_tree.column(c, width=w, anchor="w" if c in ("operator", "object") else "center", stretch=c in ("operator", "object"))

    def log(self, message: str) -> None:
        self.progress_var.set(str(message))

    def set_busy(self, busy: bool) -> None:
        self.btn_get.configure(state=tk.DISABLED if busy else tk.NORMAL)

    def selected_tree(self) -> Optional[ttk.Treeview]:
        return self.main_tree

    def selected_addr(self) -> Optional[int]:
        sel = self.main_tree.selection()
        if not sel:
            return None
        tags = self.main_tree.item(sel[0], "tags")
        if tags:
            for t in tags:
                if str(t).startswith("addr:"):
                    try:
                        return int(str(t).split(":", 1)[1])
                    except Exception:
                        pass
        vals = self.main_tree.item(sel[0], "values")
        if vals:
            # fallback: find address by displayed NUMKOD can be ambiguous; use first matching decoded row.
            try:
                shown = int(vals[0])
                mode = self.mode_var.get()
                table = "reports" if mode == "reports" else "protocols" if mode == "protocols" else "settings"
                row = self.db.conn.execute(f"SELECT address FROM {table} WHERE NUMKOD=? OR address=? ORDER BY address LIMIT 1", (str(shown), shown)).fetchone()
                if row:
                    return int(row["address"])
            except Exception:
                pass
        return None

    def _wanted(self, addr: int) -> bool:
        mode = self.mode_var.get()
        k = kind_for_addr(addr)
        if mode == "all":
            return k in ("report", "report_v2", "protocol_short", "protocol_graph", "bscan", "setting")
        if mode == "reports":
            return k in ("report", "report_v2")
        if mode == "protocols":
            return k in ("protocol_short", "protocol_graph", "bscan")
        if mode == "settings":
            return k == "setting"
        return False

    def _report_display_values(self, idx_row: sqlite3.Row) -> list[str]:
        addr = int(idx_row["address"])
        r = self.db.row_by_addr("reports", addr)
        if not r:
            return [native_visible_num_for_addr(addr), "", "", "", "", "", "", "", "", ""]
        return [
            _native_num_from_report_row(r, addr),
            str(r["DATEFORM"] or ""),
            str(r["TIMEFORM"] or ""),
            _operator_name_for_code(r["KODOPERA"], r["NAMEOPERA"]) or str(r["KODOPERA"] or ""),
            str(r["NUMVERS"] or ""),
            str(r["NUMPRIB"] or ""),
            _short_typevar(r["TYPEVAR"]),
            str(r["NUMOBJ"] or ""),
            str(r["CODEDEF"] or "0"),
            str(r["PROTOCOL"] or ""),
        ]

    def _protocol_display_values(self, idx_row: sqlite3.Row) -> list[str]:
        addr = int(idx_row["address"])
        r = self.db.row_by_addr("protocols", addr)
        if not r:
            return [native_visible_num_for_addr(addr), "", "", "", "", "", "", "", "", ""]
        return [
            str(r["NUMKOD"] or addr % 1000), str(r["DATEFORM"] or ""), str(r["TIMEFORM"] or ""), _operator_name_for_code(r["KODOPERA"], r["NAMEOPERA"]) or str(r["KODOPERA"] or ""),
            str(r["NUMVERS"] or ""), str(r["NUMPRIB"] or ""), _short_typevar(r["TYPEVAR"]), str(r["NUMOBJ"] or ""), str(r["SETTING_NO"] or ""), str(r["DEFEKT"] or ""),
        ]

    def _setting_display_values(self, idx_row: sqlite3.Row) -> list[str]:
        addr = int(idx_row["address"])
        r = self.db.row_by_addr("settings", addr)
        if not r:
            return [native_visible_num_for_addr(addr), "", "", "", "", "", "", "", str(idx_row["status"] or "")]
        return [
            str(r["NUMKOD"] or addr % 1000), str(r["DATEFORM"] or ""), str(r["TIMEFORM"] or ""), _operator_name_for_code(r["KODOPERA"], r["NAMEOPERA"]) or str(r["KODOPERA"] or ""),
            str(r["NUMVERS"] or ""), str(r["NUMPRIB"] or ""), str(r["SETTING_NO"] or ""), _short_typevar(r["TYPEVAR"]), "готово" if idx_row["decoded"] else str(idx_row["status"] or ""),
        ]

    def reload_idx_tables(self) -> None:
        for item in self.main_tree.get_children():
            self.main_tree.delete(item)
        mode = self.mode_var.get()
        if mode == "reports":
            buckets = ("reports",)
        elif mode == "protocols":
            buckets = ("protocols",)
        elif mode == "settings":
            buckets = ("settings",)
        else:
            buckets = ("reports", "protocols", "settings", "other")
        qmarks = ",".join("?" for _ in buckets)
        rows = list(self.db.conn.execute(f"SELECT * FROM idx_catalog WHERE bucket IN ({qmarks}) ORDER BY address", buckets)) if buckets else []
        for row in rows:
            addr = int(row["address"])
            if mode == "reports" or row["bucket"] == "reports":
                vals = self._report_display_values(row)
            elif mode == "protocols" or row["bucket"] == "protocols":
                vals = self._protocol_display_values(row)
            elif mode == "settings" or row["bucket"] == "settings":
                vals = self._setting_display_values(row)
            else:
                vals = [str(addr), "", "", "", "", "", "", str(row["kind"]), str(row["status"] or "")] if mode == "settings" else [str(addr)] + [""] * (len(self._column_defs()) - 1)
            self.main_tree.insert("", tk.END, values=vals, tags=(f"addr:{addr}",))
        counts = {b: self.db.conn.execute("SELECT count(*) AS c FROM idx_catalog WHERE bucket=?", (b,)).fetchone()["c"] for b in ("reports", "protocols", "settings", "other")}
        self.status_var.set(f"Отчёты: {counts['reports']}   Протоколы: {counts['protocols']}   Настройки: {counts['settings']}   Прочее: {counts['other']}")

    def open_selected_detail(self, forced_bucket: Optional[str] = None) -> None:
        addr = self.selected_addr()
        if addr is None:
            return
        k = kind_for_addr(addr)
        raw_row = self.db.get_raw_by_addr(addr)
        if not raw_row:
            messagebox.showinfo("Данные", "Эта запись ещё не получена. Нажмите кнопку получения данных.")
            return
        if k in ("report", "report_v2"):
            NativeReportSheet(self, self.db, addr)
            return
        return super().open_selected_detail(forced_bucket)




# ---------------------------------------------------------------------------
# Native basket + report decode corrections, round48.
#
# Original PelengPC keeps two levels:
#   1) raw 55 Idx catalogue at FormReadData+0x30C;
#   2) visible/request basket at +0x3B4.
# For report ranges 10000..29999 the basket contains one container per
# base=(addr//100)*100, even when the container has exactly one child row.
# Double-click expands/loads all child rows base+1..base+max_row that were
# present in the original 55 list.  This block implements that presentation
# without changing the transport/decoder core above.
# ---------------------------------------------------------------------------

def _native_header_version(header: bytes) -> str:
    """Version string built like original category_struct NUMVERS from 55 header."""
    try:
        if len(header) >= 6:
            major = int(header[4])
            minor = int(header[5])
            if 0 < major < 100 and 0 <= minor < 100:
                return f"{major:02d}.{minor:02d}"
    except Exception:
        pass
    return "06.43"


def _native_header_device(header: bytes) -> str:
    try:
        v = device_no_from_header(header)
        return "" if v is None else str(v)
    except Exception:
        return ""


def _report_header_for_addr(db: PelengDB, addr: int) -> bytes:
    try:
        raw_row = db.get_raw_by_addr(int(addr))
        if raw_row is not None:
            hx = str(raw_row["header_hex"] or "")
            if hx:
                return bytes.fromhex(hx)
    except Exception:
        pass
    try:
        idx_row = db.conn.execute("SELECT header_hex FROM idx_catalog WHERE address=?", (int(addr),)).fetchone()
        if idx_row and idx_row["header_hex"]:
            return bytes.fromhex(str(idx_row["header_hex"]))
    except Exception:
        pass
    return b""


def _apply_native_report_session_meta(db: PelengDB, addr: int, fields: dict[str, str], header: bytes | None = None) -> dict[str, str]:
    """Patch report meta that original DLL takes from EXE header16, not from payload."""
    h = header or _report_header_for_addr(db, addr)
    if h:
        fields = dict(fields)
        # Keep NUMVERS from payload (e.g. real 6.42); header/default may be 6.43.
        dev = _native_header_device(h)
        if dev:
            fields["NUMPRIB"] = dev
    # Original report date/time for clean live records is in payload+7:
    # [DD MM YY HH MM].  Keep this as a hard correction because generic
    # fallback may prefer older/false windows.
    try:
        raw_row = db.get_raw_by_addr(int(addr))
        raw = bytes(raw_row["raw"]) if raw_row else b""
        if raw:
            d, t = best_datetime(raw, (0x07,))
            if d:
                fields["DATEFORM"] = d
                fields["TIMEFORM"] = t
    except Exception:
        pass
    return fields


def _report_children_idx_rows(db: PelengDB, base: int) -> list[sqlite3.Row]:
    return list(db.conn.execute(
        """
        SELECT * FROM idx_catalog
        WHERE bucket='reports' AND address>=? AND address<?
        ORDER BY address
        """,
        (int(base), int(base) + 100),
    ))


def _report_container_map(db: PelengDB) -> list[dict[str, Any]]:
    """Build visible report containers from idx_catalog, preserving first 55 order."""
    rows = list(db.conn.execute("SELECT * FROM idx_catalog WHERE bucket='reports' ORDER BY source_order, address"))
    by_base: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for row in rows:
        addr = int(row["address"])
        base = native_report_container_base(addr)
        c = by_base.get(base)
        if c is None:
            c = {"base": base, "first_addr": addr, "first_order": int(row["source_order"]), "rows": []}
            by_base[base] = c
            order.append(base)
        c["rows"].append(row)
        # Original group descriptor stores max row and visible basket stores base;
        # for our table we keep the first real child as representative because
        # decoded visible NUMKOD is addr%10000 (10101 -> 101), not base/100.
        if int(row["source_order"]) < int(c["first_order"]):
            c["first_addr"] = addr
            c["first_order"] = int(row["source_order"])
    return [by_base[b] for b in order]


def _best_report_row_for_container(db: PelengDB, children: list[sqlite3.Row]) -> tuple[int, sqlite3.Row | None]:
    """Return representative address and decoded report row for visible container."""
    if not children:
        return 0, None
    # Prefer the smallest address/row because the expanded report sheet is row-ordered.
    addrs = sorted(int(r["address"]) for r in children)
    for addr in addrs:
        rr = db.row_by_addr("reports", addr)
        if rr:
            return addr, rr
    return addrs[0], None


class NativeReportSheetBasketExact(NativeReportSheet):
    """Report sheet where selected_addr is a container representative."""

    def __init__(self, master: tk.Misc, db: PelengDB, selected_addr: int, group_base: int | None = None):
        self.forced_group_base = int(group_base) if group_base is not None else None
        super().__init__(master, db, selected_addr)

    def _rows_for_group(self) -> list[sqlite3.Row]:
        if self.forced_group_base is not None:
            self.group_base = self.forced_group_base
        rows = list(self.db.conn.execute(
            "SELECT * FROM reports WHERE address>=? AND address<? ORDER BY address",
            (self.group_base, self.group_base + 100),
        ))
        if not rows:
            row = self.db.row_by_addr("reports", self.selected_addr)
            rows = [row] if row else []
        return rows


class NativeLikeBasketExactApp(NativeLikeApp):
    """Native-like UI with original-style report basket containers."""

    def _fetch_and_decode_addr(self, ser: PelengSerial, addr: int) -> dict[str, Any]:
        res = super()._fetch_and_decode_addr(ser, addr)
        # The original DecodeReportV1 receives EXE buffer = header16+payload,
        # so NUMVERS/NUMPRIB come from 55 header, not bytes 4/5 of live payload.
        try:
            if kind_for_addr(addr) in ("report", "report_v2"):
                h = self.header or _report_header_for_addr(self.db, addr)
                if h:
                    self.db.conn.execute(
                        "UPDATE reports SET NUMPRIB=COALESCE(NULLIF(?,''),NUMPRIB) WHERE address=?",
                        (_native_header_device(h), int(addr)),
                    )
                    # Keep the DB transaction policy of the caller: parent may be inside bulk.
                    if not getattr(self.db, "bulk_depth", 0) > 0:
                        self.db.conn.commit()
        except Exception:
            pass
        return res

    def _report_container_values(self, container: dict[str, Any]) -> list[str]:
        children = list(container.get("rows") or [])
        rep_addr, report_row = _best_report_row_for_container(self.db, children)
        if report_row:
            vals = self._report_display_values(report_row)
            # Display native session meta from the 55 header without mutating the
            # reports table. This also repairs old DB rows saved by bad builds.
            h = _report_header_for_addr(self.db, rep_addr)
            dev = _native_header_device(h) if h else ""
            # Column order: num,date,time,operator,version,device,typevar,object,defects,protocol.
            # Keep version from payload; header/default may show 6.43 for 6.42 records.
            if dev:
                vals[5] = dev
        else:
            vals = [native_visible_num_for_addr(rep_addr), "", "", "", "", "", "", "", "", ""]
        return vals

    def reload_idx_tables(self) -> None:
        for item in self.main_tree.get_children():
            self.main_tree.delete(item)
        mode = self.mode_var.get()

        if mode == "reports":
            containers = _report_container_map(self.db)
            for c in containers:
                base = int(c["base"])
                rep_addr = int(c["first_addr"])
                vals = self._report_container_values(c)
                tags = (f"addr:{rep_addr}", f"base:{base}", f"children:{len(c.get('rows') or [])}")
                self.main_tree.insert("", tk.END, values=vals, tags=tags)
        else:
            # Non-report views are not grouped by hundred; original only groups 10000..29999.
            if mode == "protocols":
                buckets = ("protocols",)
            elif mode == "settings":
                buckets = ("settings",)
            else:
                buckets = ("reports", "protocols", "settings", "other")
            qmarks = ",".join("?" for _ in buckets)
            rows = list(self.db.conn.execute(f"SELECT * FROM idx_catalog WHERE bucket IN ({qmarks}) ORDER BY address", buckets)) if buckets else []
            if mode == "all":
                # In All mode still collapse reports into containers first, then append the rest.
                seen_report_bases: set[int] = set()
                for c in _report_container_map(self.db):
                    base = int(c["base"])
                    seen_report_bases.add(base)
                    rep_addr = int(c["first_addr"])
                    self.main_tree.insert("", tk.END, values=self._report_container_values(c), tags=(f"addr:{rep_addr}", f"base:{base}"))
                rows = [r for r in rows if r["bucket"] != "reports"]
            for row in rows:
                addr = int(row["address"])
                if row["bucket"] == "protocols":
                    vals = self._protocol_display_values(row)
                elif row["bucket"] == "settings":
                    vals = self._setting_display_values(row)
                else:
                    vals = [str(addr)] + [""] * (len(self._column_defs()) - 1)
                self.main_tree.insert("", tk.END, values=vals, tags=(f"addr:{addr}",))

        counts_raw = {b: self.db.conn.execute("SELECT count(*) AS c FROM idx_catalog WHERE bucket=?", (b,)).fetchone()["c"] for b in ("reports", "protocols", "settings", "other")}
        report_containers = len(_report_container_map(self.db))
        self.status_var.set(
            f"Отчёты: {report_containers} контейнеров / {counts_raw['reports']} строк   "
            f"Протоколы: {counts_raw['protocols']}   Настройки: {counts_raw['settings']}   Прочее: {counts_raw['other']}"
        )

    def selected_addr(self) -> Optional[int]:
        sel = self.main_tree.selection()
        if not sel:
            return None
        tags = self.main_tree.item(sel[0], "tags")
        for t in tags:
            if str(t).startswith("addr:"):
                try:
                    return int(str(t).split(":", 1)[1])
                except Exception:
                    pass
        return super().selected_addr()

    def selected_base(self) -> Optional[int]:
        sel = self.main_tree.selection()
        if not sel:
            return None
        tags = self.main_tree.item(sel[0], "tags")
        for t in tags:
            if str(t).startswith("base:"):
                try:
                    return int(str(t).split(":", 1)[1])
                except Exception:
                    pass
        addr = self.selected_addr()
        return native_report_container_base(addr) if addr is not None and kind_for_addr(addr) in ("report", "report_v2") else None

    def open_selected_detail(self, forced_bucket: Optional[str] = None) -> None:
        addr = self.selected_addr()
        if addr is None:
            return
        k = kind_for_addr(addr)
        if k in ("report", "report_v2"):
            base = self.selected_base() or native_report_container_base(addr)
            # If the representative raw was not decoded yet but children are, still open.
            has_any = self.db.conn.execute("SELECT count(*) AS c FROM reports WHERE address>=? AND address<?", (base, base + 100)).fetchone()["c"]
            if not has_any:
                messagebox.showinfo("Данные", "Контейнер ещё не получен/не дешифрован. Нажмите получение данных.")
                return
            NativeReportSheetBasketExact(self, self.db, addr, base)
            return
        if k in ("protocol_short", "protocol_graph", "bscan"):
            if not self.db.row_by_addr("protocols", addr):
                messagebox.showinfo("Данные", "Протокол ещё не получен/не дешифрован. Нажмите получение данных.")
                return
            NativeAscanProtocolSheet(self, self.db, addr)
            return
        return super().open_selected_detail(forced_bucket)




# ---------------------------------------------------------------------------
# User-editable report header/operator settings integration
# ---------------------------------------------------------------------------

def _ui_open_report_fields_settings(self) -> None:
    ReportFieldsSettingsDialog(self, self.db, on_saved=self._after_report_fields_saved)


def _ui_after_report_fields_saved(self) -> None:
    try:
        _v25_apply_report_fields_to_decoded_sqlite(_v20_user_db_path(None))
    except Exception:
        pass
    try:
        self.reload_idx_tables()
    except Exception:
        pass


# Patch fetch/decode so newly received rows immediately receive the configured
# operator name.  This is deliberately display/business metadata only; it does
# not affect raw bytes or transport.
try:
    _orig_basket_fetch_and_decode = NativeLikeBasketExactApp._fetch_and_decode_addr  # type: ignore[name-defined]
    def _fetch_and_decode_addr_with_operator_directory(self, ser, addr):
        res = _orig_basket_fetch_and_decode(self, ser, addr)
        try:
            _apply_operator_directory_to_addr(self.db, int(addr))
        except Exception:
            pass
        return res
    NativeLikeBasketExactApp._fetch_and_decode_addr = _fetch_and_decode_addr_with_operator_directory  # type: ignore[name-defined]
except Exception:
    pass

try:
    NativeLikeBasketExactApp.open_report_fields_settings = _ui_open_report_fields_settings  # type: ignore[name-defined]
    NativeLikeBasketExactApp._after_report_fields_saved = _ui_after_report_fields_saved  # type: ignore[name-defined]
except Exception:
    pass

# Attach PostgreSQL actions after all UI classes are defined.
try:
    NativeLikeBasketExactApp.open_pg_settings = _ui_pg_open_settings  # type: ignore[name-defined]
    NativeLikeBasketExactApp.export_selected_to_postgres = _ui_pg_export_selected  # type: ignore[name-defined]
    NativeLikeBasketExactApp.export_all_to_postgres = _ui_pg_export_all  # type: ignore[name-defined]
    NativeReportSheet.export_to_postgres = _report_sheet_export_to_pg  # type: ignore[name-defined]
    NativeReportSheetBasketExact.export_to_postgres = _report_sheet_export_to_pg  # type: ignore[name-defined]
except Exception:
    pass


def main() -> None:
    app = NativeLikeBasketExactApp()
    app.mainloop()


# main() call moved to the end after v10/v11 monkey patches.

# ---------------------------------------------------------------------------
# v10 protocol-sheet fix: auto-load linked setting on double click and draw
# A-scan with native-like autoscaled orientation inside the Развертка rectangle.
# This block is intentionally appended as monkey patches so transport, basket,
# PostgreSQL export, reports and stored decoders from v9 remain untouched.
# ---------------------------------------------------------------------------

def _v10_setting_raw_is_good(raw: bytes | None, addr: int) -> bool:
    if not raw:
        return False
    try:
        if len(raw) < min(LEN_NASTR2, 0x80):
            return False
        return bool(setting_record_acceptable(raw, addr))
    except Exception:
        return len(raw) >= LEN_NASTR2


def _v10_protocol_dependency_addrs(db: PelengDB, addr: int) -> tuple[int, int]:
    """Return (setting_addr, graph_addr) for a protocol, using DB row and raw fallback."""
    setting_addr = 0
    graph_addr = graph_addr_for_protocol(int(addr))
    row = db.row_by_addr("protocols", int(addr))
    if row:
        try:
            if str(row["SETTING_ADDR"] or "").isdigit():
                setting_addr = int(row["SETTING_ADDR"])
        except Exception:
            pass
        try:
            if str(row["GRAPH_ADDR"] or "").isdigit():
                graph_addr = int(row["GRAPH_ADDR"])
        except Exception:
            pass
    raw_row = db.get_raw_by_addr(int(addr))
    if raw_row:
        raw = bytes(raw_row["raw"])
        if not setting_addr:
            try:
                setting_addr = protocol_setting_addr_643(raw)
            except Exception:
                setting_addr = 0
        try:
            # Also refresh the protocols row when it was decoded by an older build.
            if not row:
                fields = decode_protocol_ascan_643(raw, int(addr), None, strict=False)
                db.save_protocol(int(raw_row["id"]), int(addr), fields)
                row = db.row_by_addr("protocols", int(addr))
                if row and str(row["SETTING_ADDR"] or "").isdigit():
                    setting_addr = int(row["SETTING_ADDR"])
                if row and str(row["GRAPH_ADDR"] or "").isdigit():
                    graph_addr = int(row["GRAPH_ADDR"])
        except Exception:
            pass
    return setting_addr, graph_addr


def _v10_fetch_addr_safely(app: NativeLikeBasketExactApp, addr: int, reason: str) -> bool:  # type: ignore[name-defined]
    """Fetch one dependency with existing transport code; never raises to UI."""
    try:
        ser = app.ensure_serial()
        app.status_var.set(f"Запрашиваю {reason}: {addr}...")
        app.update_idletasks()
        res = app._fetch_and_decode_addr(ser, int(addr))
        try:
            app.reload_idx_tables()
        except Exception:
            pass
        ok = bool(res.get("ok") or res.get("decoded")) if isinstance(res, dict) else True
        app.status_var.set(f"{reason}: {addr} {'получено' if ok else 'получено с диагностикой'}")
        return ok
    except Exception as exc:
        try:
            app.status_var.set(f"Не удалось запросить {reason} {addr}: {exc}")
        except Exception:
            pass
        return False


def _v10_ensure_protocol_dependencies(app: NativeLikeBasketExactApp, addr: int) -> None:  # type: ignore[name-defined]
    """Native-like behavior for protocol sheet: load linked setting before opening.

    Original viewer shows setting values on the A-scan protocol page.  If the
    user collected only protocols/reports, the linked NASTR2 record may not yet
    be present in SQLite.  Fetch it on double-click with the same 42 path.
    """
    setting_addr, graph_addr = _v10_protocol_dependency_addrs(app.db, int(addr))
    # Always prefer a fresh/correct NASTR2 for the sheet.  Bad/stale settings are
    # common after older experimental builds, so validate length/layout first.
    if setting_addr:
        raw_row = app.db.get_raw_by_addr(setting_addr)
        raw = bytes(raw_row["raw"]) if raw_row else None
        if not _v10_setting_raw_is_good(raw, setting_addr):
            _v10_fetch_addr_safely(app, setting_addr, "настройку протокола")
        else:
            # Ensure decoded settings table exists for display/export.
            if not app.db.row_by_addr("settings", setting_addr):
                try:
                    fields, params = decode_setting_643(raw, setting_addr, app.device_no, strict=False)
                    app.db.save_setting(int(raw_row["id"]), setting_addr, fields, params)
                except Exception:
                    pass
    # Optional graph dependency: request only if the chosen linked frame is absent.
    # If the device returns short 0x56 for 6000+n, this remains diagnostic and the
    # sheet will still use graph from the selected 4000-record tail.
    if graph_addr and graph_addr != int(addr) and not app.db.get_raw_by_addr(graph_addr):
        _v10_fetch_addr_safely(app, graph_addr, "связанную запись графика")


try:
    _v10_orig_open_selected_detail = NativeLikeBasketExactApp.open_selected_detail  # type: ignore[name-defined]
    def _v10_open_selected_detail(self, forced_bucket: Optional[str] = None):
        addr = self.selected_addr()
        if addr is not None and kind_for_addr(addr) in ("protocol_short", "protocol_graph", "bscan"):
            _v10_ensure_protocol_dependencies(self, int(addr))
        return _v10_orig_open_selected_detail(self, forced_bucket)
    NativeLikeBasketExactApp.open_selected_detail = _v10_open_selected_detail  # type: ignore[name-defined]
except Exception:
    pass


def _v10_decode_setting_params(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    # Re-read after auto-fetch; do not trust stale self.setting_raw captured before.
    try:
        if self.setting_addr:
            rr = self.db.get_raw_by_addr(int(self.setting_addr))
            self.setting_raw = bytes(rr["raw"]) if rr else None
    except Exception:
        pass
    if self.setting_raw:
        try:
            return decode_nastr2_params_643(self.setting_raw, int(self.setting_addr))
        except Exception as exc:
            return {"error": str(exc)}
    return {}


def _v10_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    """Draw scaled A-scan strictly inside the native rectangle.

    Device graph samples are byte values around baseline 0x8C, but on live data
    the visible signal is often the inverted delta (baseline - sample).  The old
    renderer used a fixed native scale and clipped most of the curve below the
    rectangle.  This version auto-selects orientation and gain, preserving the
    original field placement while making the trace visible.
    """
    c = self.graph_canvas
    c.delete("all")
    w, h = 360, 230
    ml, mr, mt, mb = 14, 14, 12, 28
    pw, ph = w - ml - mr, h - mt - mb
    x0, y0, x1, y1 = ml, mt, w - mr, h - mb
    c.create_rectangle(x0, y0, x1, y1, outline="#222")
    for i in range(1, 9):
        x = x0 + pw * i / 10
        c.create_line(x, y0, x, y1, fill="#d5d5d5", dash=(1, 7))
    for i in range(1, 6):
        y = y0 + ph * i / 7
        c.create_line(x0, y, x1, y, fill="#d5d5d5", dash=(1, 7))

    if "samples" not in self.graph:
        c.create_text(w // 2, h // 2, text=self.graph.get("error", "Нет графика"), fill="#555", width=w-30)
        return
    samples = [int(s) & 0xFF for s in (self.graph.get("samples") or [])]
    if len(samples) < 2:
        return

    # Native bottom baseline and autoscaled visible delta.
    baseline_y = y1 - 18
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")

    normal = [s - GRAPH_BASELINE for s in samples]
    inverted = [GRAPH_BASELINE - s for s in samples]
    # Pick orientation that has more positive visible energy.
    pos_norm = sum(max(0, d) for d in normal)
    pos_inv = sum(max(0, d) for d in inverted)
    deltas = inverted if pos_inv >= pos_norm else normal
    max_pos = max([max(0, d) for d in deltas] or [1])
    if max_pos <= 0:
        # Fallback: map min/max into the box if all deltas are negative/flat.
        mn, mx = min(samples), max(samples)
        rng = max(1, mx - mn)
        deltas = [(mx - s) for s in samples]
        max_pos = max(1, max(deltas))
    gain = min(8.0, max(0.45, (ph * 0.78) / max(1, max_pos)))

    def x_of_i(i: int) -> float:
        return x0 + (i / max(1, len(samples) - 1)) * pw
    def y_of_delta(d: float) -> float:
        y = baseline_y - max(0, d) * gain
        if y < y0 + 3:
            y = y0 + 3
        if y > y1 - 2:
            y = y1 - 2
        return y

    pts: list[float] = []
    for i, d in enumerate(deltas):
        pts.extend((x_of_i(i), y_of_delta(d)))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)

    # Cursor/zone marker.  Keep it inside the graph rectangle.
    try:
        duration = int(self.zones.get("duration_t10") or self.setting_params.get("duration_t10") or 7920)
        raw_x = int(self.zones.get("vs1_start_raw", 0) or 0)
        if raw_x:
            x = x0 + raw_x / max(1, duration) * pw
            x = max(x0 + 1, min(x1 - 1, x))
            cy = y0 + ph * 0.55
            c.create_line(x, y0 + 8, x, y1, fill="#333")
            c.create_line(x - 8, cy, x + 8, cy, fill="#333")
    except Exception:
        pass

try:
    NativeAscanProtocolSheet._decode_setting_params = _v10_decode_setting_params  # type: ignore[name-defined]
    NativeAscanProtocolSheet._draw_native_graph = _v10_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass


# ---------------------------------------------------------------------------
# v11 exact NASTR2 setting decoder from matched setting №26 XML + raw 0x176.
# This replaces the earlier heuristic layout selector for full live NASTR2.
# It is intentionally pure decode/display: no transport, basket, report, or
# PostgreSQL export behavior is changed.
# ---------------------------------------------------------------------------

def _v11_map_probe_enabled(code: int) -> str:
    return {0: "-", 1: "раздельн.", 2: "совмещ."}.get(int(code), str(code))

def _v11_map_low_high(code: int) -> str:
    return {0: "-", 1: "низкая", 2: "высокая"}.get(int(code), str(code))

def _v11_map_onoff(code: int) -> str:
    return "вкл." if int(code) else "отключена"

def _v11_format_date_time_setting(record: bytes) -> tuple[str, str]:
    # Confirmed for setting 26: raw[0x07..0x0B] = DD MM YY HH MM.
    try:
        dd, mm, yy, hh, mi = (safe_u8(record, 0x07), safe_u8(record, 0x08), safe_u8(record, 0x09), safe_u8(record, 0x0A), safe_u8(record, 0x0B))
        if 1 <= dd <= 31 and 1 <= mm <= 12 and 0 <= hh <= 23 and 0 <= mi <= 59:
            return f"{dd:02d}.{mm:02d}.20{yy:02d}", f"{hh:02d}:{mi:02d}"
    except Exception:
        pass
    return best_datetime(record, (0x07, 0x06, 0x08))

def _v11_decode_nastr2_params_643(record: bytes, addr: Optional[int] = None) -> dict[str, Any]:
    """Exact live NASTR2 decoder for VAGON 6.42/6.43 setting records.

    Verified against matched sample:
      setting address 1026 / setting №26,
      raw payload length 0x176,
      original XML "ПАРАМЕТРЫ НАСТРОЙКИ № 26".

    Important offsets are relative to the clean 0x42 payload:
      [0x00]=addr, [0x02]=0x0176.
    """
    setting_no = (int(addr) - 1000) if addr is not None and 1000 <= int(addr) <= 1999 else max(0, safe_le16(record, 0) - 1000)
    sdate, stime = _v11_format_date_time_setting(record)

    typevar = safe_le16(record, 0x0E, 0)
    if not typevar and setting_no in SETTING_TYPEVAR_FALLBACK_BY_NO:
        typevar = SETTING_TYPEVAR_FALLBACK_BY_NO[setting_no]
    info = typevar_info_643(typevar)

    speed = safe_le16(record, 0x28, 5900)
    if not (1000 <= int(speed) <= 10000):
        speed = 5900
    angle = safe_le16(record, 0x2A, 0)
    if not (0 <= int(angle) <= 90):
        angle = 0

    # Regulated parameters.
    freq_raw = safe_u8(record, 0x12, 0)                 # 25 -> 2.5 MHz
    freq_mhz = freq_raw / 10.0 if freq_raw else 0.0
    thickness_mm = safe_le16(record, 0x2A, 0) / 10.0    # setting 26 has 0.0; same word is angle for 0° axial branch.
    amplitude_probe_code = safe_u8(record, 0x10, 0)     # 1 -> низкая
    cutoff_pct = safe_le16(record, 0x3E, 0)             # 5
    blocking_code = safe_u8(record, 0x40, 0)            # 0 -> отключена

    # Probe / PEP.
    probe_no = reverse_digit_field(record, 0x1C, 6)     # 03 01 00 04 04 02 -> 244013
    probe_enabled = _v11_map_probe_enabled(safe_u8(record, 0x0F, 0))
    probe_time_raw = safe_u8(record, 0x2D, 0)           # 250 -> 2.50 us
    probe_time_us_float = probe_time_raw / 100.0

    # Sensitivity.
    extra_gain_db = safe_u8(record, 0x45, 0)
    required_sens_db = -safe_u8(record, 0x46, 0)
    actual_sens_db = -safe_u8(record, 0x47, 0)
    gain_db = safe_u8(record, 0x48, 0)
    extra_gain_enabled = "-"                           # XML #26: disabled, separate enable flag not needed for display.

    # Sweep / razvertka.
    so_start_raw = safe_le16(record, 0x57, 0)           # 124 -> T12.4us
    so_end_raw = safe_le16(record, 0x59, 0)             # 270 -> T27.0us
    duration_raw = safe_le16(record, 0x5B, 0)           # 33 -> 792.0us via type 0x12
    delay_raw = safe_le16(record, 0x5D, 0)              # 0
    sweep_type_raw = safe_u8(record, 0x5F, 0)           # 1 -> 120%

    # Zones.
    vs1_threshold = safe_u8(record, 0x67, 0)
    vs1_method = safe_u8(record, 0x68, 0)
    vs1_start = safe_le16(record, 0x69, 0)
    vs1_end = safe_le16(record, 0x6B, 0)

    vs2_threshold = safe_u8(record, 0x71, 0)
    vs2_method = safe_u8(record, 0x72, 0)
    vs2_start = safe_le16(record, 0x73, 0)
    vs2_end = safe_le16(record, 0x75, 0)

    # ARU / VRCH.
    aru_start = 0
    aru_end = 0
    vrch_type_raw = safe_u8(record, 0x7B, 0)
    vrch_start = safe_le16(record, 0x84, 0)
    vrch_end = safe_le16(record, 0x86, 0)
    vrch_amp = safe_u8(record, 0x8D, 0)
    vrch_shape = safe_u8(record, 0x8E, 0)
    before_vrch = safe_u8(record, 0x89, 0)
    after_vrch = safe_u8(record, 0x8A, 0)

    # Fixed parameters.
    probing_period = safe_u8(record, 0x24, 0)
    fixed_threshold = safe_u8(record, 0x95, 0)
    probing_freq_hz = safe_le16(record, 0x4A, 0)
    additional_mark = format_coord13(0, speed, angle)

    params: dict[str, Any] = {
        "layout": "exact_xml26_v11",
        "setting_no": setting_no,
        "operator_code": f"{safe_u8(record, 0x0D, 0):02d}",
        "date": sdate,
        "time": stime,
        "typevar": typevar_display(typevar),
        "typevar_code": typevar,
        "object": info.get("object", ""),
        "detail": info.get("detail", ""),
        "ntd": info.get("ntd", ""),

        "freq_mhz_raw": freq_raw,
        "freq_mhz": f"{freq_mhz:.1f}" if freq_mhz else "",
        "sound_speed": speed,
        "thickness_mm": f"{thickness_mm:.1f}",
        "amplitude_probe_raw": amplitude_probe_code,
        "amplitude_probe": _v11_map_low_high(amplitude_probe_code),
        "cutoff_pct": cutoff_pct,
        "blocking": _v11_map_onoff(blocking_code),

        "probe_no": probe_no,
        "probe_enabled": probe_enabled,
        "angle_deg": int(angle),
        "probe_time_raw": probe_time_raw,
        "probe_time_us": f"{probe_time_us_float:.2f}",

        "gain_db": gain_db,
        "required_sens_db": required_sens_db,
        "actual_sens_db": actual_sens_db,
        "extra_gain_db": extra_gain_db,
        "extra_gain_enabled": extra_gain_enabled,

        "sweep_type_raw": sweep_type_raw,
        "sweep_type": SWEEP_TYPES.get(sweep_type_raw, f"unknown({sweep_type_raw})"),
        "sweep_duration_raw": duration_raw,
        "sweep_duration": format_sweep12(duration_raw, speed, angle),
        "duration_t10": int(round(sweep12_to_time_us(duration_raw) * 10.0)) if duration_raw else 0,
        "sweep_delay_raw": delay_raw,
        "sweep_delay": format_sweep12(delay_raw, speed, angle),
        "w_sweep_enabled": "-",
        "envelope_enabled": "-",

        "magnifier_enabled": "-",
        "magnifier_type": "руч.мет.",
        "so_start_raw": so_start_raw,
        "so_start": format_coord13(so_start_raw, speed, angle),
        "so_end_raw": so_end_raw,
        "so_end": format_coord13(so_end_raw, speed, angle),

        "vs1_threshold_pct": vs1_threshold,
        "vs1_method_raw": vs1_method,
        "vs1_method": VS1_METHODS.get(vs1_method, f"unknown({vs1_method})"),
        "vs1_start_raw": vs1_start,
        "vs1_start": format_coord13(vs1_start, speed, angle),
        "vs1_end_raw": vs1_end,
        "vs1_end": format_coord13(vs1_end, speed, angle),

        "vs2_threshold_pct": vs2_threshold,
        "vs2_method_raw": vs2_method,
        "vs2_method": VS2_METHODS.get(vs2_method, f"unknown({vs2_method})"),
        "vs2_start_raw": vs2_start,
        "vs2_start": format_coord13(vs2_start, speed, angle),
        "vs2_end_raw": vs2_end,
        "vs2_end": format_coord13(vs2_end, speed, angle),

        "aru_enabled": "-",
        "aru_start": format_coord13(aru_start, speed, angle),
        "aru_end": format_coord13(aru_end, speed, angle),
        "vrch_type_raw": vrch_type_raw,
        "vrch_type": "отключена" if vrch_type_raw == 0 else str(vrch_type_raw),
        "vrch_indication": "-",
        "vrch_start_raw": vrch_start,
        "vrch_start": format_coord13(vrch_start, speed, angle),
        "vrch_end_raw": vrch_end,
        "vrch_end": format_coord13(vrch_end, speed, angle),
        "vrch_amp_db": vrch_amp,
        "vrch_shape": vrch_shape,
        "before_vrch_db": before_vrch,
        "after_vrch_db": after_vrch,

        "probing_period": probing_period,
        "fixed_threshold_pct": fixed_threshold,
        "probing_freq_hz": probing_freq_hz,
        "additional_mark": additional_mark,
    }
    return params

# Replace old heuristic setting decoder with the XML/raw verified decoder.
decode_nastr2_params_643 = _v11_decode_nastr2_params_643

# Make the generic setting detail window show the newly decoded fields too.
try:
    FIELD_LABELS.update({
        "amplitude_probe": "Ампл. зонд.",
        "cutoff_pct": "Отсечка, %",
        "blocking": "Блокировка",
        "sweep_delay": "Задержка",
        "magnifier_enabled": "Лупа: вкл.",
        "magnifier_type": "Лупа: вид",
        "so_start": "Нач. зоны ВС",
        "so_end": "Конец зоны ВС",
        "probing_period": "Пер. зондирования",
        "fixed_threshold_pct": "Фикс. порог, %",
        "probing_freq_hz": "Част. зонд., Гц",
        "additional_mark": "Доп. метка",
    })
except Exception:
    pass



# ---------------------------------------------------------------------------
# v12 protocol reverse pass: original-like protocol sheet source model
# ---------------------------------------------------------------------------
# Findings from zapis2.exe:
# - The A-scan widget copies exactly 0xF4 bytes from a descriptor-selected
#   graph block and draws 0xF3 samples in a logical rectangle 0x118 x 0x0C8.
# - X scale is native_width/244, Y scale is native_height/140.
# - The protocol sheet uses the linked NASTR2 record for the bottom settings
#   block and typevar-derived Object/Detail/NTD text.  Therefore a double-click
#   must fetch 1000+setting_no when it is absent/stale.
# - Some live devices return short 0x56 diagnostics for 6000+n, while the full
#   graph is present in the paired 4000+n record.  Try both 4000+n and 6000+n,
#   but ignore short frames as graph sources.

_NATIVE_GRAPH_W = 0x118  # 280
_NATIVE_GRAPH_H = 0x0C8  # 200


def _v12_graph_candidate_addrs(addr: int, row: Any = None) -> list[int]:
    """Return plausible full graph/protocol records for a visible protocol row."""
    addr = int(addr)
    cand: list[int] = []
    def add(a: int) -> None:
        if 4000 <= int(a) <= 6999 and int(a) not in cand:
            cand.append(int(a))
    add(addr)
    try:
        if row is not None and str(row["GRAPH_ADDR"] or "").isdigit():
            add(int(row["GRAPH_ADDR"]))
    except Exception:
        pass
    # Native-visible protocol number can be represented by either 4000+n or
    # 6000+n; live 6000 sometimes returns only 0x56, so 4000+n is essential.
    slot = addr % 1000
    if 6000 <= addr <= 6999:
        add(4000 + slot)
    if 4000 <= addr <= 4999:
        add(6000 + slot)
    return cand


def _v12_graph_raw_score(raw: bytes | None) -> int:
    if not raw:
        return -10**9
    # Reject short 0x56-like records as graph sources; they may contain useful
    # links but not a full 0xF4 sample block with stable context.
    if len(raw) < GRAPH_COPY_LEN + 0x20:
        return -10**8 + len(raw)
    try:
        off = find_ascan_graph_offset_643(raw)
        samples = bytes(raw[off:off + GRAPH_COPY_LEN])[:GRAPH_DRAW_COUNT]
        if len(samples) < 32:
            return -10**7
        return _score_graph_block(samples) + min(len(raw), 0x3A6) // 16
    except Exception:
        return -10**7 + len(raw)


def _v12_protocol_setting_addr(db: PelengDB, addr: int) -> int:  # type: ignore[name-defined]
    """Find linked NASTR2 address from row first, then clean protocol raw."""
    row = db.row_by_addr("protocols", int(addr))
    if row:
        for key in ("SETTING_ADDR",):
            try:
                s = str(row[key] or "")
                if s.isdigit() and 1000 <= int(s) <= 1999:
                    return int(s)
            except Exception:
                pass
        try:
            s = str(row["SETTING_NO"] or "")
            if s.isdigit() and 0 < int(s) <= 999:
                return 1000 + int(s)
        except Exception:
            pass
    rr = db.get_raw_by_addr(int(addr))
    if rr:
        raw = bytes(rr["raw"])
        try:
            v = protocol_setting_no_643(raw)
            if 0 < int(v) <= 999:
                return 1000 + int(v)
        except Exception:
            pass
    return 0


def _v12_ensure_protocol_dependencies(app: NativeLikeBasketExactApp, addr: int) -> None:  # type: ignore[name-defined]
    """Fetch linked setting and the paired graph/protocol record if needed."""
    addr = int(addr)
    setting_addr = _v12_protocol_setting_addr(app.db, addr)
    if setting_addr:
        rr = app.db.get_raw_by_addr(setting_addr)
        raw = bytes(rr["raw"]) if rr else None
        if not _v10_setting_raw_is_good(raw, setting_addr):
            _v10_fetch_addr_safely(app, setting_addr, "настройку протокола")
            rr = app.db.get_raw_by_addr(setting_addr)
            raw = bytes(rr["raw"]) if rr else None
        # Always refresh decoded settings row through the current v11 exact
        # decoder; older DB rows can contain stale heuristic parameters.
        if raw:
            try:
                fields, params = decode_setting_643(raw, setting_addr, app.device_no, strict=False)
                raw_id = int(rr["id"]) if rr else 0
                app.db.save_setting(raw_id, setting_addr, fields, params)
            except Exception:
                pass

    row = app.db.row_by_addr("protocols", addr)
    # Fetch paired graph/protocol candidate only when the selected row has no
    # visible graph source.  This keeps double-click responsive for normal rows.
    best_score = -10**9
    best_addr = 0
    for a in _v12_graph_candidate_addrs(addr, row):
        rr = app.db.get_raw_by_addr(a)
        sc = _v12_graph_raw_score(bytes(rr["raw"]) if rr else None)
        if sc > best_score:
            best_score = sc
            best_addr = a
    if best_score < 0:
        for a in _v12_graph_candidate_addrs(addr, row):
            if a != addr and not app.db.get_raw_by_addr(a):
                _v10_fetch_addr_safely(app, a, "связанную запись графика")
                break


try:
    _v12_orig_open_selected_detail = NativeLikeBasketExactApp.open_selected_detail  # type: ignore[name-defined]
    def _v12_open_selected_detail(self, forced_bucket: Optional[str] = None):
        addr = self.selected_addr()
        if addr is not None and kind_for_addr(int(addr)) in ("protocol_short", "protocol_graph", "bscan"):
            _v12_ensure_protocol_dependencies(self, int(addr))
        return _v12_orig_open_selected_detail(self, forced_bucket)
    NativeLikeBasketExactApp.open_selected_detail = _v12_open_selected_detail  # type: ignore[name-defined]
except Exception:
    pass


def _v12_decode_setting_params(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    # Re-read linked setting after v12 auto-fetch/refresh.
    try:
        self.setting_addr = _v12_protocol_setting_addr(self.db, int(self.addr)) or self.setting_addr
        if self.setting_addr:
            rr = self.db.get_raw_by_addr(int(self.setting_addr))
            self.setting_raw = bytes(rr["raw"]) if rr else None
    except Exception:
        pass
    if self.setting_raw:
        try:
            return decode_nastr2_params_643(self.setting_raw, int(self.setting_addr))
        except Exception as exc:
            return {"error": str(exc)}
    return {}


def _v12_decode_graph(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    row = getattr(self, "row", None)
    best: Optional[dict[str, Any]] = None
    best_score = -10**9
    self.graph_source_raw = b""
    self.graph_source_addr = 0
    seen: set[int] = set()
    for a in _v12_graph_candidate_addrs(int(self.addr), row):
        if a in seen:
            continue
        seen.add(a)
        rr = self.db.get_raw_by_addr(a)
        raw = bytes(rr["raw"]) if rr else (self.protocol_raw if a == int(self.addr) else b"")
        if not raw:
            continue
        # Ignore short summary/diagnostic frames as graph sources.
        if len(raw) < GRAPH_COPY_LEN + 0x20:
            continue
        try:
            g = decode_ascan_graph_643(raw)
            samples = bytes(g.get("samples") or [])
            score = _score_graph_block(samples) + (len(raw) // 16)
            if score > best_score:
                best_score = score
                best = dict(g)
                best["source_addr"] = a
                best["source_len"] = len(raw)
                self.graph_source_raw = raw
                self.graph_source_addr = a
        except Exception:
            continue
    if best is not None:
        return best
    return {"error": "Нет полного блока графика: перечитайте протокол 4000+n/связанную запись"}


def _v12_sheet_typevar_info(self: NativeAscanProtocolSheet) -> dict[str, str]:  # type: ignore[name-defined]
    # Prefer exact linked setting, because the original protocol sheet uses the
    # setting/typevar to print Object, Detail and NTD.
    p = getattr(self, "setting_params", {}) or {}
    code = 0
    try:
        code = int(p.get("typevar_code") or 0)
    except Exception:
        code = 0
    if not code:
        try:
            code = self._typevar_code()
        except Exception:
            code = 0
    if code:
        return typevar_info_643(code)
    return {"object": p.get("object", ""), "detail": p.get("detail", ""), "ntd": p.get("ntd", "")}


def _v12_object_number_value(self: NativeAscanProtocolSheet) -> str:  # type: ignore[name-defined]
    # Protocol page object data is in RESULTS2 row; use saved value first, then
    # original reverse digit candidates.  Do not use NASTR2, which has no object number.
    return self._not_empty(
        self._row_get("NUMOBJ"),
        best_reverse_digit_field(self.protocol_raw, ((0x11, 0x0B), (0x10, 0x0B), (0x21, 0x0C), (0x20, 0x0C)), 12),
    )


def _v12_smelting_value(self: NativeAscanProtocolSheet) -> str:  # type: ignore[name-defined]
    return self._not_empty(
        self._row_get("SMELTING"),
        best_reverse_digit_field(self.protocol_raw, ((0x35, 0x07), (0x34, 0x07), (0x33, 0x07), (0x45, 0x07)), 8),
        "0",
    )


def _v12_factory_value(self: NativeAscanProtocolSheet) -> str:  # type: ignore[name-defined]
    # These are protocol/result object fields, not NASTR2 setting fields.
    for s in (self._row_get("INDMAKER"),):
        if str(s).strip():
            return str(s).strip()
    for off in (0x3C, 0x4C, 0x2F):
        v = safe_le16(self.protocol_raw, off, 0)
        if 0 < v < 10000:
            return str(v)
    return ""


def _v12_year_value(self: NativeAscanProtocolSheet) -> str:  # type: ignore[name-defined]
    for s in (self._row_get("MAKETIME"),):
        if str(s).strip():
            return str(s).strip()
    for off in (0x3E, 0x4E, 0x30):
        v = safe_le16(self.protocol_raw, off, 0)
        if 1900 <= v <= 2099:
            return str(v)
        if 1 <= v <= 99:
            return f"20{v:02d}"
    return ""


def _v12_side_value(self: NativeAscanProtocolSheet) -> str:  # type: ignore[name-defined]
    # Side is a protocol row/object field.  Settings do not carry the object's side.
    for off in (0x40, 0x50, 0x60):
        if len(self.protocol_raw) > off:
            b = self.protocol_raw[off]
            if b in (0, 1, 2, 3):
                return {0: "лев", 1: "прав", 2: "обе", 3: "обе"}.get(b, "")
    return ""


def _v12_neck_value(self: NativeAscanProtocolSheet) -> str:  # type: ignore[name-defined]
    info_obj = (_v12_sheet_typevar_info(self).get("object", "") or "").lower()
    if "колес" in info_obj and "ось" not in info_obj:
        return ""
    for off in (0x41, 0x51, 0x61):
        if len(self.protocol_raw) > off:
            b = self.protocol_raw[off]
            if b in (0, 1, 2, 3):
                return {0: "с кольцами", 1: "без колец", 2: "с буксой", 3: "с буксой"}.get(b, "")
    return ""


def _v12_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    """Original-like A-scan graph: fixed native box, auto-scaled visible trace.

    Original zapis2.exe graph facts:
      width=0x118 (280), height=0x0C8 (200), sample block=0xF4,
      draw count=0xF3, xscale=280/244, yscale=200/140.
    Tk has a downward Y axis, while the original CDC page uses a transformed
    logical rectangle, so we draw the same samples but auto-fit their visible
    delta inside the field to avoid clipping the trace below the rectangle.
    """
    c = self.graph_canvas
    c.delete("all")
    # Keep native proportions inside our larger canvas.
    w, h = 360, 230
    native_w, native_h = 280, 200
    x0 = 14
    y0 = 12
    x1 = x0 + native_w
    y1 = y0 + native_h
    pw, ph = native_w, native_h
    c.create_rectangle(x0, y0, x1, y1, outline="#222")
    for i in range(1, 9):
        x = x0 + pw * i / 10
        c.create_line(x, y0, x, y1, fill="#d5d5d5", dash=(1, 7))
    for i in range(1, 6):
        y = y0 + ph * i / 7
        c.create_line(x0, y, x1, y, fill="#d5d5d5", dash=(1, 7))
    if "samples" not in self.graph:
        c.create_text((x0 + x1) // 2, (y0 + y1) // 2, text=self.graph.get("error", "Нет графика"), fill="#555", width=native_w-20)
        return
    samples = [int(s) & 0xFF for s in (self.graph.get("samples") or [])][:GRAPH_DRAW_COUNT]
    if len(samples) < 2:
        return

    # Native baseline is near bottom.  Use auto gain but keep baseline visible.
    baseline_y = y1 - 18
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")
    normal = [s - GRAPH_BASELINE for s in samples]
    inverted = [GRAPH_BASELINE - s for s in samples]
    pos_norm = sum(max(0, d) for d in normal)
    pos_inv = sum(max(0, d) for d in inverted)
    deltas = inverted if pos_inv >= pos_norm else normal
    max_pos = max([max(0, d) for d in deltas] or [1])
    if max_pos <= 0:
        mn, mx = min(samples), max(samples)
        deltas = [(mx - s) for s in samples]
        max_pos = max(1, max(deltas))
    # Smaller scale than v10 when spikes are extreme; this mimics native page
    # where a 0..140 logical amplitude is compressed into 200 logical units.
    gain = min(5.5, max(0.35, (ph * 0.72) / max(1, max_pos)))

    pts: list[float] = []
    for i, d in enumerate(deltas):
        x = x0 + (i / max(1, len(samples) - 1)) * pw
        y = baseline_y - max(0, d) * gain
        y = max(y0 + 2, min(y1 - 2, y))
        pts.extend((x, y))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)

    # Native-like cursor/zone marker, clipped inside graph field.
    try:
        duration = int((self.setting_params or {}).get("duration_t10") or self.zones.get("duration_t10") or 7920)
        raw_x = int(self.zones.get("vs1_start_raw", 0) or 0)
        if raw_x:
            x = x0 + raw_x / max(1, duration) * pw
            x = max(x0 + 1, min(x1 - 1, x))
            cy = y0 + ph * 0.55
            c.create_line(x, y0 + 8, x, y1, fill="#333")
            c.create_line(x - 8, cy, x + 8, cy, fill="#333")
    except Exception:
        pass


try:
    NativeAscanProtocolSheet._decode_setting_params = _v12_decode_setting_params  # type: ignore[name-defined]
    NativeAscanProtocolSheet._decode_graph = _v12_decode_graph  # type: ignore[name-defined]
    NativeAscanProtocolSheet._typevar_info = _v12_sheet_typevar_info  # type: ignore[name-defined]
    NativeAscanProtocolSheet._object_number_value = _v12_object_number_value  # type: ignore[name-defined]
    NativeAscanProtocolSheet._smelting_value = _v12_smelting_value  # type: ignore[name-defined]
    NativeAscanProtocolSheet._factory_value = _v12_factory_value  # type: ignore[name-defined]
    NativeAscanProtocolSheet._year_value = _v12_year_value  # type: ignore[name-defined]
    NativeAscanProtocolSheet._side_value = _v12_side_value  # type: ignore[name-defined]
    NativeAscanProtocolSheet._neck_value = _v12_neck_value  # type: ignore[name-defined]
    NativeAscanProtocolSheet._draw_native_graph = _v12_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass


# ---------------------------------------------------------------------------
# v13 protocol reverse patch: exact original descriptors for the right-side
# defect metrics and native-like graph overlays (ВС1/ВС2/defect marker).
# This is intentionally presentation/decode-only and does not alter transport,
# basket, PostgreSQL export, or stored raw records.
# ---------------------------------------------------------------------------

import math as _v13_math


def real48_to_float_v13(data: bytes, off: int) -> float:
    """Decode Borland/Turbo Pascal 6-byte Real48 used by zapis2 protocol fields.

    Original zapis2.exe reader: FUN_00423253 / FUN_004086BB.
    Format: byte0 exponent, bytes1..5 mantissa/sign; zero exponent means 0.0.
    """
    if off < 0 or off + 6 > len(data):
        return 0.0
    b0, b1, b2, b3, b4, b5 = data[off:off + 6]
    if (b0 | b1 | b2 | b3 | b4 | b5) == 0 or b0 == 0:
        return 0.0
    sign = -1.0 if (b5 & 0x80) else 1.0
    mant = ((b5 & 0x7F) << 32) | (b4 << 24) | (b3 << 16) | (b2 << 8) | b1
    try:
        return sign * (1.0 + mant / float(1 << 39)) * (2.0 ** (b0 - 129))
    except Exception:
        return 0.0


def _v13_fmt_metric_1(v: float) -> str:
    try:
        if not _v13_math.isfinite(float(v)):
            return "0.0"
        if abs(float(v)) < 0.05:
            return "0.0"
        return f"{float(v):.1f}"
    except Exception:
        return "0.0"


def decode_defect_643(record: bytes, speed_m_s: int = 5900, angle_deg: float = 0.0) -> dict[str, Any]:  # type: ignore[no-redef]
    """Decode RESULTS2 defect/right-block metrics using original zapis2 descriptors.

    Confirmed from the native descriptor table around 0x004B42E0:
      Кол. отражений луча M       offset 0x48, type 0x38 signed byte
      Глубина дефекта Y, мм       offset 0x157, type 0x03 Real48
      Расст.до проекции деф. X    offset 0x151, type 0x03 Real48
      Расстояние по лучу R, мм    offset 0x14B, type 0x03 Real48
      Коэф. выявляемости, дБ      offset 0x166, type 0x38 signed byte

    These fields are not calculated from raw[0x60]; they are stored/rendered
    by zapis2 as typed descriptor fields.  If a short record does not contain
    them, return native blank/zero defaults.
    """
    y = real48_to_float_v13(record, 0x157)
    x = real48_to_float_v13(record, 0x151)
    r = real48_to_float_v13(record, 0x14B)
    m = safe_i8(record, 0x48, 0) if len(record) > 0x48 else 0
    k = safe_i8(record, 0x166, 0) if len(record) > 0x166 else 0

    # Keep old defect-code text as an optional diagnostic, but do not use it as
    # the right-side metric source.
    numeric_code = best_reverse_digit_field(record, ((0x21, 0x07), (0x22, 0x07)), 8)
    mapped_defect = ""
    if numeric_code.isdigit():
        try:
            mapped_defect = orig_defect_text(int(numeric_code))
        except Exception:
            mapped_defect = ""

    return {
        "defect_present": bool(mapped_defect),
        "defect_code_text": f"{numeric_code} — {mapped_defect}" if mapped_defect else "",
        "defect_code_numeric": numeric_code if mapped_defect else "",
        "defect_raw_t10": 0,
        "defect_y": float(y),
        "defect_x": float(x),
        "defect_r": float(r),
        "defect_t": 0.0,
        "defect_m": str(int(m)),
        "detectability_db": str(int(k)),
        "defect_y_text": _v13_fmt_metric_1(y),
        "defect_x_text": _v13_fmt_metric_1(x),
        "defect_r_text": _v13_fmt_metric_1(r),
        "descriptor_source": "zapis2:0x4B42E0",
    }


def _v13_zone_values(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    """Prefer linked NASTR2 setting zones; fallback to graph/protocol snapshot."""
    p = getattr(self, "setting_params", {}) or {}
    z = getattr(self, "zones", {}) or {}
    out: dict[str, Any] = {}
    def pick(name: str, default: Any = 0) -> Any:
        v = p.get(name)
        if v not in (None, "", 0, "0"):
            return v
        return z.get(name, default)
    for k in ("duration_t10", "vs1_start_raw", "vs1_end_raw", "vs2_start_raw", "vs2_end_raw", "vrch_start_raw", "vrch_end_raw", "extra_start_raw", "extra_end_raw"):
        out[k] = pick(k, 0)
    # v34 graph snapshot uses extra_*, exact NASTR2 uses vrch_*.
    if not out.get("vrch_start_raw"):
        out["vrch_start_raw"] = out.get("extra_start_raw", 0)
    if not out.get("vrch_end_raw"):
        out["vrch_end_raw"] = out.get("extra_end_raw", 0)
    return out


def _v13_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    """Draw A-scan exactly inside the native 'Развертка' rectangle.

    Additions over v12:
      * use linked-setting zone timings when available;
      * draw ВС1/ВС2/ВРЧ markers inside the graph field;
      * draw defect marker from the original R/Y/X descriptor metrics;
      * auto-scale trace vertically so low live traces remain visible.
    """
    c = self.graph_canvas
    c.delete("all")
    native_w, native_h = 280, 200
    x0, y0 = 12, 10
    x1, y1 = x0 + native_w, y0 + native_h
    pw, ph = native_w, native_h
    c.create_rectangle(x0, y0, x1, y1, outline="#222")

    # Native-like dotted grid.
    for i in range(1, 10):
        x = x0 + pw * i / 10
        c.create_line(x, y0, x, y1, fill="#d9d9d9", dash=(1, 7))
    for i in range(1, 7):
        y = y0 + ph * i / 7
        c.create_line(x0, y, x1, y, fill="#d9d9d9", dash=(1, 7))

    zone = _v13_zone_values(self)
    try:
        duration = int(zone.get("duration_t10") or (getattr(self, "setting_params", {}) or {}).get("duration_t10") or 7920)
    except Exception:
        duration = 7920
    duration = max(1, duration)

    def x_by_t10(raw_x: Any) -> float:
        try:
            rx = float(raw_x or 0)
        except Exception:
            rx = 0.0
        return max(x0, min(x1, x0 + (rx / duration) * pw))

    # Zones first, behind the trace.
    def zone_band(a: Any, b: Any, label: str, dash: tuple[int, int] = (2, 3)) -> None:
        try:
            aa, bb = int(a or 0), int(b or 0)
        except Exception:
            return
        if aa <= 0 and bb <= 0:
            return
        if bb < aa:
            aa, bb = bb, aa
        xa, xb = x_by_t10(aa), x_by_t10(bb)
        if xb - xa < 1:
            c.create_line(xa, y0 + 3, xa, y1 - 3, fill="#666", dash=dash)
        else:
            c.create_rectangle(xa, y0 + 1, xb, y1 - 1, fill="#eeeeee", stipple="gray12", outline="")
            c.create_line(xa, y0 + 3, xa, y1 - 3, fill="#666", dash=dash)
            c.create_line(xb, y0 + 3, xb, y1 - 3, fill="#666", dash=dash)
        if label:
            c.create_text((xa + xb) / 2, y0 + 10, text=label, fill="#555", font=("Arial", 7))

    zone_band(zone.get("vs1_start_raw"), zone.get("vs1_end_raw"), "ВС1")
    zone_band(zone.get("vs2_start_raw"), zone.get("vs2_end_raw"), "ВС2")
    zone_band(zone.get("vrch_start_raw"), zone.get("vrch_end_raw"), "ВРЧ", dash=(1, 5))

    if "samples" not in self.graph:
        c.create_text((x0 + x1) // 2, (y0 + y1) // 2, text=self.graph.get("error", "Нет графика"), fill="#555", width=native_w - 20)
        return
    samples = [int(s) & 0xFF for s in (self.graph.get("samples") or [])][:GRAPH_DRAW_COUNT]
    if len(samples) < 2:
        return

    baseline_y = y1 - 18
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")

    normal = [s - GRAPH_BASELINE for s in samples]
    inverted = [GRAPH_BASELINE - s for s in samples]
    pos_norm = sum(max(0, d) for d in normal)
    pos_inv = sum(max(0, d) for d in inverted)
    deltas = inverted if pos_inv >= pos_norm else normal
    max_pos = max([max(0, d) for d in deltas] or [1])
    if max_pos <= 0:
        mn, mx = min(samples), max(samples)
        deltas = [(mx - s) for s in samples]
        max_pos = max(1, max(deltas))
    # Compress like native page; do not let a spike clip the whole trace.
    gain = min(5.0, max(0.30, (ph * 0.70) / max(1, max_pos)))
    pts: list[float] = []
    for i, d in enumerate(deltas):
        x = x0 + (i / max(1, len(samples) - 1)) * pw
        y = baseline_y - max(0, d) * gain
        y = max(y0 + 2, min(y1 - 2, y))
        pts.extend((x, y))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)

    # Defect marker from exact original descriptor fields.  Original screenshot
    # shows a small cross in the graph field; use R to position horizontally and
    # Y only as an approximate vertical cue because native axis transform is not
    # fully exposed in the decompiler.
    try:
        r_mm = float((self.defect or {}).get("defect_r") or 0.0)
        y_mm = float((self.defect or {}).get("defect_y") or 0.0)
        speed = float((getattr(self, "setting_params", {}) or {}).get("sound_speed") or 5900)
        if r_mm > 0 and speed > 0:
            raw_t10 = int(round((r_mm * 20000.0) / speed))
            mx = x_by_t10(raw_t10)
            # Use Y relative to R when plausible, otherwise middle of the field.
            ratio = max(0.05, min(0.95, y_mm / r_mm)) if r_mm > 1 and y_mm >= 0 else 0.50
            my = y1 - 8 - ratio * (ph * 0.70)
            my = max(y0 + 8, min(y1 - 8, my))
            c.create_line(mx - 8, my, mx + 8, my, fill="#333")
            c.create_line(mx, my - 8, mx, my + 8, fill="#333")
    except Exception:
        pass


# Patch protocol sheet methods for v13.
try:
    NativeAscanProtocolSheet._draw_native_graph = _v13_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass



# ---------------------------------------------------------------------------
# v14 protocol/settings correction pass
# ---------------------------------------------------------------------------
# Goals:
#   1) match native A-scan graph orientation: peak must go UP, not down;
#   2) draw ВС1/ВС2/ВРЧ zones visibly inside the native graph rectangle;
#   3) compute the defect marker from original descriptor metrics, and if those
#      are zero, fall back to the strongest graph echo peak;
#   4) re-read linked NASTR2 setting on protocol double-click and use it for all
#      setting-derived fields;
#   5) keep NUMVERS from real record payload (for example 6.42) and use the
#      55 header only for NUMPRIB/device metadata.
# This block is deliberately appended as monkey patches so transport, basket,
# reports and PostgreSQL export remain unchanged.


def _v14_idx_header_for_addr(db: PelengDB, addr: int) -> bytes:
    """Return true session 55 header for any address; prefer idx_catalog."""
    try:
        row = db.conn.execute("SELECT header_hex FROM idx_catalog WHERE address=?", (int(addr),)).fetchone()
        if row and row["header_hex"]:
            h = bytes.fromhex(str(row["header_hex"]))
            if len(h) >= 0x10:
                return h[:0x10]
    except Exception:
        pass
    try:
        rr = db.get_raw_by_addr(int(addr))
        if rr and rr["header_hex"]:
            h = bytes.fromhex(str(rr["header_hex"]))
            if len(h) >= 0x10:
                return h[:0x10]
    except Exception:
        pass
    # Fallback: use any header in the catalogue from the same session.
    try:
        row = db.conn.execute("SELECT header_hex FROM idx_catalog WHERE header_hex IS NOT NULL AND header_hex<>'' ORDER BY source_order LIMIT 1").fetchone()
        if row and row["header_hex"]:
            h = bytes.fromhex(str(row["header_hex"]))
            if len(h) >= 0x10:
                return h[:0x10]
    except Exception:
        pass
    return b""


def _v14_header_version(header: bytes) -> str:
    try:
        if len(header) >= 6:
            major, minor = int(header[4]), int(header[5])
            if 0 <= major < 100 and 0 <= minor < 100:
                return f"{major:02d}.{minor:02d}"
    except Exception:
        pass
    return ""


def _v14_header_device(header: bytes) -> str:
    try:
        v = device_no_from_header(header)
        return "" if v is None else str(v)
    except Exception:
        return ""


def _v14_patch_row_session_meta(db: PelengDB, table: str, addr: int) -> None:
    """Patch decoded DB row with session device; keep payload firmware version."""
    if table not in ("reports", "protocols", "settings"):
        return
    h = _v14_idx_header_for_addr(db, int(addr))
    dev = _v14_header_device(h)
    if not dev:
        return
    try:
        # Firmware/software version is decoded from the record payload.  Do not
        # overwrite real 6.42 payload values with a stale/default 55-header 6.43.
        db.conn.execute(
            f"UPDATE {table} SET NUMPRIB=COALESCE(NULLIF(?,''),NUMPRIB) WHERE address=?",
            (dev, int(addr)),
        )
        if not getattr(db, "bulk_depth", 0) > 0:
            db.conn.commit()
    except Exception:
        pass


try:
    _v14_orig_fetch_decode = NativeLikeBasketExactApp._fetch_and_decode_addr  # type: ignore[name-defined]
    def _v14_fetch_and_decode_addr(self, ser: PelengSerial, addr: int) -> dict[str, Any]:  # type: ignore[name-defined]
        res = _v14_orig_fetch_decode(self, ser, int(addr))
        k = kind_for_addr(int(addr))
        if k in ("report", "report_v2"):
            _v14_patch_row_session_meta(self.db, "reports", int(addr))
        elif k in ("protocol_short", "protocol_graph", "bscan"):
            _v14_patch_row_session_meta(self.db, "protocols", int(addr))
        elif k == "setting":
            _v14_patch_row_session_meta(self.db, "settings", int(addr))
        return res
    NativeLikeBasketExactApp._fetch_and_decode_addr = _v14_fetch_and_decode_addr  # type: ignore[name-defined]
except Exception:
    pass


try:
    _v14_orig_protocol_display = NativeLikeBasketExactApp._protocol_display_values  # type: ignore[name-defined]
    def _v14_protocol_display_values(self, idx_row: sqlite3.Row) -> list[str]:  # type: ignore[name-defined]
        vals = _v14_orig_protocol_display(self, idx_row)
        try:
            h = _v14_idx_header_for_addr(self.db, int(idx_row["address"]))
            ver, dev = _v14_header_version(h), _v14_header_device(h)
            # Column order: num,date,time,operator,version,device,typevar,object,setting,defekt
            if ver:
                vals[4] = ver
            if dev:
                vals[5] = dev
        except Exception:
            pass
        return vals
    NativeLikeBasketExactApp._protocol_display_values = _v14_protocol_display_values  # type: ignore[name-defined]

    _v14_orig_setting_display = NativeLikeBasketExactApp._setting_display_values  # type: ignore[name-defined]
    def _v14_setting_display_values(self, idx_row: sqlite3.Row) -> list[str]:  # type: ignore[name-defined]
        vals = _v14_orig_setting_display(self, idx_row)
        try:
            h = _v14_idx_header_for_addr(self.db, int(idx_row["address"]))
            ver, dev = _v14_header_version(h), _v14_header_device(h)
            # Column order: num,date,time,operator,version,device,setting,typevar,status
            if ver:
                vals[4] = ver
            if dev:
                vals[5] = dev
        except Exception:
            pass
        return vals
    NativeLikeBasketExactApp._setting_display_values = _v14_setting_display_values  # type: ignore[name-defined]
except Exception:
    pass


def _v14_decode_defect(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    """Use graph-source/raw RESULTS2 record for descriptor metrics, not stale protocol row."""
    try:
        speed = int((getattr(self, "setting_params", {}) or {}).get("sound_speed") or safe_le16(self.protocol_raw, 0x77, 5900) or 5900)
    except Exception:
        speed = 5900
    try:
        angle = float((getattr(self, "setting_params", {}) or {}).get("angle_deg") or 0.0)
    except Exception:
        angle = 0.0
    raw = getattr(self, "graph_source_raw", b"") or getattr(self, "graph_raw", b"") or getattr(self, "protocol_raw", b"")
    try:
        return decode_defect_643(raw, speed, angle)
    except Exception:
        try:
            return decode_defect_643(self.protocol_raw, speed, angle)
        except Exception:
            return {}


def _v14_zone_values(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    p = getattr(self, "setting_params", {}) or {}
    z = getattr(self, "zones", {}) or {}
    out: dict[str, Any] = {}
    def pick(*names: str, default: Any = 0) -> Any:
        for n in names:
            v = p.get(n)
            if v not in (None, "", 0, "0"):
                return v
        for n in names:
            v = z.get(n)
            if v not in (None, "", 0, "0"):
                return v
        return default
    out["duration_t10"] = pick("duration_t10", default=7920)
    out["vs1_start_raw"] = pick("vs1_start_raw", default=0)
    out["vs1_end_raw"] = pick("vs1_end_raw", default=0)
    out["vs2_start_raw"] = pick("vs2_start_raw", default=0)
    out["vs2_end_raw"] = pick("vs2_end_raw", default=0)
    out["vrch_start_raw"] = pick("vrch_start_raw", "extra_start_raw", default=0)
    out["vrch_end_raw"] = pick("vrch_end_raw", "extra_end_raw", default=0)
    out["vs1_threshold_pct"] = pick("vs1_threshold_pct", "vs1_threshold", default=50)
    out["vs2_threshold_pct"] = pick("vs2_threshold_pct", "vs2_threshold", default=50)
    return out


def _v14_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    """Native-oriented A-scan graph.

    The original CDC graph uses amplitude = sample - 0x8C with Y axis upward.
    v13 auto-selected inverted orientation, which could put the end echo spike
    downward.  v14 uses the native orientation and only scales/clips into the
    visible 280x200 page rectangle.
    """
    c = self.graph_canvas
    c.delete("all")
    native_w, native_h = 280, 200
    x0, y0 = 12, 10
    x1, y1 = x0 + native_w, y0 + native_h
    pw, ph = native_w, native_h
    c.create_rectangle(x0, y0, x1, y1, outline="#222")
    # dotted grid
    for i in range(1, 10):
        x = x0 + pw * i / 10.0
        c.create_line(x, y0, x, y1, fill="#d0d0d0", dash=(1, 6))
    for i in range(1, 7):
        y = y0 + ph * i / 7.0
        c.create_line(x0, y, x1, y, fill="#d0d0d0", dash=(1, 6))

    zone = _v14_zone_values(self)
    try:
        duration = int(zone.get("duration_t10") or 7920)
    except Exception:
        duration = 7920
    duration = max(1, duration)
    baseline_y = y1 - 22

    def x_by_t10(raw_x: Any) -> float:
        try:
            rx = float(raw_x or 0)
        except Exception:
            rx = 0.0
        return max(x0, min(x1, x0 + (rx / duration) * pw))

    def threshold_y(pct: Any) -> float:
        try:
            pval = float(pct or 0)
        except Exception:
            pval = 0.0
        return max(y0 + 4, min(y1 - 4, baseline_y - (pval / 100.0) * (ph * 0.72)))

    # Draw ВС/ВРЧ zones visibly before trace, but with solid boundary lines so
    # they are visible on photographs of the monitor.
    def draw_zone(a: Any, b: Any, label: str, thr: Any = None, dash: tuple[int, int] = (3, 3)) -> None:
        try:
            aa, bb = int(a or 0), int(b or 0)
        except Exception:
            return
        if aa <= 0 and bb <= 0:
            return
        if bb < aa:
            aa, bb = bb, aa
        xa, xb = x_by_t10(aa), x_by_t10(bb)
        if xb - xa >= 2:
            c.create_rectangle(xa, y0 + 1, xb, y1 - 1, outline="", fill="#f3f3f3", stipple="gray12")
        for xx in (xa, xb):
            c.create_line(xx, y0 + 2, xx, y1 - 2, fill="#555", dash=dash, width=1)
        if thr not in (None, "", 0, "0"):
            yy = threshold_y(thr)
            c.create_line(xa, yy, xb if xb > xa else xa + 16, yy, fill="#444", dash=(2, 2), width=1)
        c.create_text((xa + xb) / 2 if xb > xa else xa + 10, y0 + 10, text=label, fill="#333", font=("Arial", 7, "bold"))

    draw_zone(zone.get("vs1_start_raw"), zone.get("vs1_end_raw"), "ВС1", zone.get("vs1_threshold_pct"), dash=(3, 3))
    draw_zone(zone.get("vs2_start_raw"), zone.get("vs2_end_raw"), "ВС2", zone.get("vs2_threshold_pct"), dash=(5, 2))
    draw_zone(zone.get("vrch_start_raw"), zone.get("vrch_end_raw"), "ВРЧ", None, dash=(1, 4))

    if "samples" not in self.graph:
        c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")
        c.create_text((x0 + x1) // 2, (y0 + y1) // 2, text=self.graph.get("error", "Нет графика"), fill="#555", width=native_w - 20)
        return
    samples = [int(s) & 0xFF for s in (self.graph.get("samples") or [])][:GRAPH_DRAW_COUNT]
    if len(samples) < 2:
        c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")
        return

    amps = [s - GRAPH_BASELINE for s in samples]
    max_pos = max([a for a in amps if a > 0] or [1])
    min_neg = min([a for a in amps if a < 0] or [0])
    # Native has logical height 200 and baseline byte 0x8C=140.  Use a gain that
    # fits positive peaks, while clipping negative noise below the baseline.
    gain = min(4.8, max(0.45, (ph * 0.72) / max(1, max_pos)))
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")
    pts: list[float] = []
    for i, a in enumerate(amps):
        x = x0 + (i / max(1, len(amps) - 1)) * pw
        y = baseline_y - a * gain
        # Allow a little noise below baseline but clip to field.
        y = max(y0 + 2, min(y1 - 2, y))
        pts.extend((x, y))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)

    # Defect/cursor marker.  Prefer exact R/Y descriptors; if absent/zero, place
    # marker at the strongest positive echo in the trace, which matches the
    # native screenshot with the end echo cross.
    mx = my = None
    try:
        r_mm = float((self.defect or {}).get("defect_r") or 0.0)
        y_mm = float((self.defect or {}).get("defect_y") or 0.0)
        speed = float((getattr(self, "setting_params", {}) or {}).get("sound_speed") or 5900)
        if r_mm > 0 and speed > 0:
            raw_t10 = int(round((r_mm * 20000.0) / speed))
            mx = x_by_t10(raw_t10)
            ratio = max(0.05, min(0.95, y_mm / r_mm)) if r_mm > 1 and y_mm >= 0 else 0.50
            my = y1 - 10 - ratio * (ph * 0.70)
    except Exception:
        mx = my = None
    if mx is None or my is None:
        try:
            # strongest positive echo, with a slight preference for the tail
            # where native screenshots show the marker/peak.
            scored = [(a + (20 if i > len(amps) * 0.80 else 0), i, a) for i, a in enumerate(amps)]
            _score, idx, a = max(scored)
            if a > 2:
                mx = x0 + (idx / max(1, len(amps) - 1)) * pw
                my = baseline_y - a * gain
        except Exception:
            pass
    if mx is not None and my is not None:
        mx = max(x0 + 8, min(x1 - 8, float(mx)))
        my = max(y0 + 8, min(y1 - 8, float(my)))
        c.create_line(mx - 8, my, mx + 8, my, fill="#222", width=1)
        c.create_line(mx, my - 8, mx, my + 8, fill="#222", width=1)


# Setting double-click: always recompute exact v11/v14 params from raw, so a row
# saved by an old decoder does not show stale values.  Keep raw tab for debug.
try:
    def _v14_setting_detail_init(self: SettingDetail, master: tk.Misc, row: sqlite3.Row, raw: bytes):  # type: ignore[name-defined]
        DetailWindow.__init__(self, master, f"Настройка {row['address']}")
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        f1 = ttk.Frame(nb, padding=8)
        nb.add(f1, text="Дешифровка")
        try:
            params = decode_nastr2_params_643(raw, int(row["address"]))
        except Exception as exc:
            params = {"error": str(exc)}
        meta_rows = []
        # Display session meta from true 55 header.
        try:
            db = master.db if hasattr(master, "db") else None
            h = _v14_idx_header_for_addr(db, int(row["address"])) if db else b""
            ver, dev = _v14_header_version(h), _v14_header_device(h)
            meta_rows.extend([
                ("№ записи", row["NUMKOD"] if "NUMKOD" in row.keys() else int(row["address"]) % 1000),
                ("Версия ПО", ver or (row["NUMVERS"] if "NUMVERS" in row.keys() else "")),
                ("№ прибора", dev or (row["NUMPRIB"] if "NUMPRIB" in row.keys() else "")),
            ])
        except Exception:
            pass
        rows = meta_rows + [(k, v) for k, v in sorted(params.items())]
        self.add_kv_tree(f1, rows)
        f2 = ttk.Frame(nb, padding=8)
        nb.add(f2, text="Raw hex")
        ttk.Button(f2, text="Сохранить RAW...", command=lambda: self.save_raw_file(raw, f"setting_{row['address']}.bin")).pack(anchor="e", pady=(0, 6))
        txt = tk.Text(f2, wrap=tk.NONE)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", hexdump_preview(raw, 4096))
        txt.configure(state=tk.DISABLED)
    SettingDetail.__init__ = _v14_setting_detail_init  # type: ignore[name-defined]
except Exception:
    pass

try:
    NativeAscanProtocolSheet._decode_defect = _v14_decode_defect  # type: ignore[name-defined]
    NativeAscanProtocolSheet._draw_native_graph = _v14_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass



# ---------------------------------------------------------------------------
# v15 settings/protocol presentation pass
# ---------------------------------------------------------------------------
# Goals:
#   1) Setting double-click must open a native-like "ПАРАМЕТРЫ НАСТРОЙКИ"
#      sheet, with decoded values placed opposite the labels, like original
#      PelengPC and the matched setting №26 XML.
#   2) Protocol sheet must always open at the top and keep the full protocol
#      page visible/scrollable, because previous fixed-page builds could appear
#      shifted/cropped depending on window manager geometry.
#   3) This pass is UI-only: transport, basket, reports, PostgreSQL export and
#      decoders are not changed.


def _v15_clean(v: Any, default: str = "-") -> str:
    if v is None:
        return default
    s = str(v).strip()
    if not s or s.lower() in ("none", "nan"):
        return default
    return s


class NativeSettingSheet(tk.Toplevel):
    """Native-like setting sheet for NASTR2/"Параметры настройки"."""

    PAGE_W = 1040
    PAGE_H = 1380

    def __init__(self, master: tk.Misc, row: sqlite3.Row, raw: bytes):
        super().__init__(master)
        self.master_app = master
        self.row = row
        self.raw = bytes(raw or b"")
        try:
            self.addr = int(row["address"])
        except Exception:
            self.addr = 0
        try:
            self.params = decode_nastr2_params_643(self.raw, self.addr)
        except Exception as exc:
            self.params = {"error": str(exc)}
        self.title("Настройка")
        self.geometry("1080x900")
        self.minsize(920, 680)
        self._build()

    def _header_device_version(self) -> tuple[str, str]:
        dev = ""
        ver = ""
        try:
            db = self.master_app.db if hasattr(self.master_app, "db") else None
            h = _v14_idx_header_for_addr(db, self.addr) if db else b""
            ver = _v14_header_version(h)
            dev = _v14_header_device(h)
        except Exception:
            pass
        if not ver:
            try: ver = str(self.row["NUMVERS"] or "")
            except Exception: pass
        if not dev:
            try: dev = str(self.row["NUMPRIB"] or "")
            except Exception: pass
        return dev, ver

    def _p(self, key: str, default: str = "-") -> str:
        return _v15_clean((self.params or {}).get(key), default)

    def _build(self) -> None:
        top = tk.Frame(self, bg="#efefef", bd=1, relief=tk.GROOVE)
        top.pack(fill=tk.X)
        for txt in ("Печать", "Сохранить", "Настройка"):
            tk.Button(top, text=txt, width=12, command=lambda: None).pack(side=tk.LEFT, padx=4, pady=6)

        outer = tk.Canvas(self, bg="#333333", highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=outer.yview)
        hsb = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=outer.xview)
        outer.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        page = tk.Canvas(outer, bg="white", width=self.PAGE_W, height=self.PAGE_H, bd=1, relief=tk.SOLID, highlightthickness=0)
        win = outer.create_window(12, 12, anchor="nw", window=page)
        page.bind("<Configure>", lambda _e: outer.configure(scrollregion=outer.bbox("all")))
        outer.bind("<Configure>", lambda e: outer.itemconfigure(win, width=max(self.PAGE_W, min(self.PAGE_W, e.width - 36))))
        self.page_canvas = page
        self._draw(page)
        self.after(80, lambda: outer.yview_moveto(0.0))

    def _t(self, x: int, y: int, text: Any, *, size: int = 9, bold: bool = False, anchor: str = "nw", width: Optional[int] = None) -> int:
        font = ("Arial", size, "bold" if bold else "normal")
        opts: dict[str, Any] = {"text": str(text or ""), "fill": "#111", "font": font, "anchor": anchor}
        if width:
            opts["width"] = width
        return self.page_canvas.create_text(x, y, **opts)

    def _sep_title(self, x: int, y: int, text: str, width: int = 360) -> None:
        self._t(x, y, text, size=11, bold=True)
        self.page_canvas.create_line(x, y + 18, x + width, y + 18, fill="#222")

    def _row(self, x: int, y: int, label: str, value: Any, *, value_x: int = 205, bold: bool = False) -> None:
        self._t(x, y, label, size=9)
        self._t(x + value_x, y, _v15_clean(value), size=10, bold=bold)

    def _draw(self, c: tk.Canvas) -> None:
        p = self.params or {}
        dev, ver = self._header_device_version()
        num = p.get("setting_no") or (self.addr - 1000 if 1000 <= self.addr <= 1999 else self.addr)
        date = self._p("date", "")
        time_s = self._p("time", "")
        operator_code = self._p("operator_code", "00")
        header_line = f"дефектоскоп УД2-102 № {dev}, {date} {time_s}, Версия {ver}".strip()

        self._t(62, 42, f"П А Р А М Е Т Р Ы   Н А С Т Р О Й К И   №{num}", size=13, bold=True)
        self._t(62, 70, header_line, size=10)

        self._row(62, 150, "Типовой вариант", p.get("typevar_code") or p.get("typevar") or "")
        self._row(560, 150, "Шифр оператора", operator_code)

        self._t(320, 230, "Р Е Г У Л И Р У Е М Ы Е   П А Р А М Е Т Р Ы", size=12, bold=True)
        c.create_line(318, 250, 710, 250, fill="#222")

        y = 300
        self._row(62, y, "Частота УЗК, МГц", self._p("freq_mhz")); y += 24
        self._row(62, y, "Скорость УЗК, м/с", self._p("sound_speed")); y += 24
        self._row(62, y, "Толщина, мм", self._p("thickness_mm")); y += 24
        self._row(62, y, "Ампл. зонд.", self._p("amplitude_probe")); y += 24
        self._row(62, y, "Отсечка, %", self._p("cutoff_pct")); y += 24
        self._row(62, y, "Блокировка", self._p("blocking")); y += 38

        self._sep_title(72, y, "П Э П", 120); y += 32
        self._row(62, y, "№ ПЭП", self._p("probe_no")); y += 24
        self._row(62, y, "вкл. ПЭП", self._p("probe_enabled")); y += 24
        self._row(62, y, "Угол ввода, град.", self._p("angle_deg")); y += 24
        self._row(62, y, "Время в ПЭП, мкс", self._p("probe_time_us")); y += 38

        self._sep_title(72, y, "Ч у в с т в и т е л ь н о с т ь", 245); y += 32
        self._row(62, y, "Усиление, дБ", self._p("gain_db")); y += 24
        self._row(62, y, "Треб. чувст., дБ", self._p("required_sens_db")); y += 24
        self._row(62, y, "Факт. чувст., дБ", self._p("actual_sens_db")); y += 24
        self._row(62, y, "Доп. усиление, дБ", self._p("extra_gain_db")); y += 24
        self._row(62, y, "Вкл. доп. усиления", self._p("extra_gain_enabled")); y += 38

        self._sep_title(72, y, "Р а з в е р т к а", 170); y += 32
        self._row(62, y, "Тип", self._p("sweep_type")); y += 24
        self._row(62, y, "Длительность", self._p("sweep_duration")); y += 24
        self._row(62, y, "Задержка", self._p("sweep_delay")); y += 24
        self._row(62, y, "W-развертка", self._p("w_sweep_enabled")); y += 24
        self._row(62, y, "Огибающая", self._p("envelope_enabled")); y += 38

        self._sep_title(72, y, "Л у п а", 100); y += 32
        self._row(62, y, "Вкл.", self._p("magnifier_enabled")); y += 24
        self._row(62, y, "Вид", self._p("magnifier_type"));

        # Right side regulated parameters.
        x = 560
        y = 330
        self._sep_title(x, y - 28, "Н а с т р о й к а   п о   С О", 285)
        self._row(x, y, "Нач. зоны ВС", self._p("so_start"), value_x=190); y += 24
        self._row(x, y, "Конец зоны ВС", self._p("so_end"), value_x=190); y += 44

        self._sep_title(x, y - 28, "З о н а   В С 1", 180)
        self._row(x, y, "Начало", self._p("vs1_start"), value_x=190); y += 24
        self._row(x, y, "Конец", self._p("vs1_end"), value_x=190); y += 24
        self._row(x, y, "Метод", self._p("vs1_method"), value_x=190); y += 24
        self._row(x, y, "Порог, %", self._p("vs1_threshold_pct"), value_x=190); y += 44

        self._sep_title(x, y - 28, "З о н а   В С 2", 180)
        self._row(x, y, "Начало", self._p("vs2_start"), value_x=190); y += 24
        self._row(x, y, "Конец", self._p("vs2_end"), value_x=190); y += 24
        self._row(x, y, "Метод", self._p("vs2_method"), value_x=190); y += 24
        self._row(x, y, "Порог, %", self._p("vs2_threshold_pct"), value_x=190); y += 44

        self._sep_title(x, y - 28, "А Р У", 80)
        self._row(x, y, "Вкл.", self._p("aru_enabled"), value_x=190); y += 24
        self._row(x, y, "Начало", self._p("aru_start"), value_x=190); y += 24
        self._row(x, y, "Конец", self._p("aru_end"), value_x=190); y += 44

        self._sep_title(x, y - 28, "В Р Ч", 80)
        self._row(x, y, "Тип ВРЧ", self._p("vrch_type"), value_x=190); y += 24
        self._row(x, y, "Индикация", self._p("vrch_indication"), value_x=190); y += 24
        self._row(x, y, "Начало", self._p("vrch_start"), value_x=190); y += 24
        self._row(x, y, "Конец", self._p("vrch_end"), value_x=190); y += 24
        self._row(x, y, "Амплитуда, дБ", self._p("vrch_amp_db"), value_x=190); y += 24
        self._row(x, y, "Форма", self._p("vrch_shape"), value_x=190); y += 24
        self._row(x, y, "До ВРЧ, дБ", self._p("before_vrch_db"), value_x=190); y += 24
        self._row(x, y, "После ВРЧ, дБ", self._p("after_vrch_db"), value_x=190); y += 44

        # Fixed params.
        self._t(330, 1185, "Ф И К С И Р О В А Н Н Ы Е   П А Р А М Е Т Р Ы", size=12, bold=True)
        c.create_line(328, 1205, 750, 1205, fill="#222")
        self._row(62, 1235, "Пер. зондирования", self._p("probing_period"))
        self._row(62, 1260, "Порог, %", self._p("fixed_threshold_pct"))
        self._row(560, 1235, "Част. зонд., Гц", self._p("probing_freq_hz"), value_x=190)
        self._row(560, 1260, "Доп. метка", self._p("additional_mark"), value_x=190)


# Replace generic setting KV table with native-like sheet.  SettingDetail is an
# existing Toplevel subclass, so copy NativeSettingSheet methods onto it before
# delegating to NativeSettingSheet.__init__().  This avoids changing all callers.
try:
    for _name in ("_header_device_version", "_p", "_build", "_t", "_sep_title", "_row", "_draw"):
        setattr(SettingDetail, _name, getattr(NativeSettingSheet, _name))  # type: ignore[name-defined]
    def _v15_setting_detail_init(self: SettingDetail, master: tk.Misc, row: sqlite3.Row, raw: bytes):  # type: ignore[name-defined]
        NativeSettingSheet.__init__(self, master, row, raw)
    SettingDetail.__init__ = _v15_setting_detail_init  # type: ignore[name-defined]
except Exception:
    pass


# Make protocol sheet reliably visible at the top, with a stable scroll region.
try:
    _v15_orig_protocol_build = NativeAscanProtocolSheet._build  # type: ignore[name-defined]
    def _v15_protocol_build(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
        _v15_orig_protocol_build(self)
        try:
            # Find the first Canvas child that is used as the scrollable outer
            # area and force top-left view after geometry managers settle.
            canvases = [w for w in self.winfo_children() if isinstance(w, tk.Canvas)]
            if canvases:
                outer = canvases[0]
                self.after(80, lambda: outer.yview_moveto(0.0))
                self.after(120, lambda: outer.xview_moveto(0.0))
        except Exception:
            pass
    NativeAscanProtocolSheet._build = _v15_protocol_build  # type: ignore[name-defined]
except Exception:
    pass


# ---------------------------------------------------------------------------
# v16 stability/UI pass: settings-sheet init fix, PostgreSQL status/password,
# graph native rendering robustness, A4/print helper, smoother sheet opening.
# ---------------------------------------------------------------------------
# This pass intentionally does not change serial transport, basket grouping,
# decoded database rows, PostgreSQL export schema, or report/protocol decoders.
# It fixes presentation/runtime problems reported after v15.

V16_PG_SETTINGS_PASSWORD = "852654"


def _v16_safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _v16_canvas_postscript_print(owner: tk.Misc, canvas: Optional[tk.Canvas] = None, title: str = "peleng_sheet") -> None:
    """Save current sheet canvas as PostScript and ask Windows to print if possible.

    Tkinter can reliably export Canvas pages to .ps on Windows without extra
    dependencies.  This is enough for the operator workflow: the sheet is an A4-like
    page in the viewer, and the user can print the generated .ps or let Windows
    route it to the default handler.
    """
    try:
        if canvas is None:
            canvas = getattr(owner, "page_canvas", None)
        if not isinstance(canvas, tk.Canvas):
            messagebox.showinfo("Печать", "Для этого окна печать доступна через экранную форму. Откройте лист и используйте системную печать/скриншот.", parent=owner)
            return
        owner.update_idletasks()
        safe_title = re.sub(r"[^A-Za-z0-9А-Яа-я_.-]+", "_", str(title or "peleng_sheet"))[:80]
        path = filedialog.asksaveasfilename(
            parent=owner,
            title="Сохранить лист для печати",
            defaultextension=".ps",
            initialfile=f"{safe_title}.ps",
            filetypes=[("PostScript", "*.ps"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        canvas.postscript(file=path, colormode="gray", pagewidth="210m", pageheight="297m", rotate=False)
        try:
            if os.name == "nt":
                os.startfile(path, "print")  # type: ignore[attr-defined]
            else:
                messagebox.showinfo("Печать", f"Лист сохранён:\n{path}", parent=owner)
        except Exception:
            messagebox.showinfo("Печать", f"Лист сохранён:\n{path}", parent=owner)
    except Exception as exc:
        messagebox.showerror("Печать", str(exc), parent=owner)


def _v16_configure_sheet_buttons(win: tk.Misc) -> None:
    """Attach real print/save behavior to top sheet buttons without rebuilding forms."""
    def walk(w: tk.Misc):
        yield w
        try:
            for ch in w.winfo_children():
                yield from walk(ch)
        except Exception:
            return
    for w in walk(win):
        try:
            txt = str(w.cget("text"))
        except Exception:
            continue
        if txt == "Печать":
            try:
                w.configure(command=lambda _w=win: _v16_canvas_postscript_print(_w, getattr(_w, "page_canvas", None), _w.title()))
            except Exception:
                pass
        elif txt == "Сохранить":
            try:
                w.configure(command=lambda _w=win: _v16_canvas_postscript_print(_w, getattr(_w, "page_canvas", None), _w.title()))
            except Exception:
                pass


# Fix v15 SettingDetail error: previous build delegated to NativeSettingSheet.__init__
# through an object that is not an instance of NativeSettingSheet, so super() raised
# "obj must be an instance or subtype of type".  Initialize Toplevel explicitly.
try:
    for _name in ("_header_device_version", "_p", "_build", "_t", "_sep_title", "_row", "_draw"):
        setattr(SettingDetail, _name, getattr(NativeSettingSheet, _name))  # type: ignore[name-defined]

    def _v16_setting_detail_init(self: SettingDetail, master: tk.Misc, row: sqlite3.Row, raw: bytes):  # type: ignore[name-defined]
        tk.Toplevel.__init__(self, master)
        self.master_app = master
        self.row = row
        self.raw = bytes(raw or b"")
        try:
            self.addr = int(row["address"])
        except Exception:
            self.addr = 0
        try:
            # Always recompute from raw 0x176; do not trust stale params_json.
            self.params = decode_nastr2_params_643(self.raw, self.addr)
        except Exception as exc:
            self.params = {"error": str(exc)}
        self.title("Настройка")
        self.geometry("1080x900")
        self.minsize(920, 680)
        self.withdraw()
        self._build()
        _v16_configure_sheet_buttons(self)
        self.update_idletasks()
        self.after(60, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    SettingDetail.__init__ = _v16_setting_detail_init  # type: ignore[name-defined]
except Exception:
    pass


# Stronger graph source selection.  The native protocol page draws from the full
# RESULTS2 record that contains a 0xF4 sample block.  Some linked 6000 records on
# live hardware are only 0x56 diagnostics and must not be selected.  Also search
# all already-loaded 4000/6000 records with the same setting number.
def _v16_graph_score(raw: bytes | None, setting_no: int = 0) -> int:
    if not raw or len(raw) < GRAPH_COPY_LEN:
        return -10**9
    try:
        off = find_ascan_graph_offset_643(raw)
        block = raw[off:off + GRAPH_COPY_LEN]
        samples = list(block[:GRAPH_DRAW_COUNT])
        if len(samples) < 32:
            return -10**9
        amps_n = [int(s) - GRAPH_BASELINE for s in samples]
        amps_i = [GRAPH_BASELINE - int(s) for s in samples]
        # We want visible positive echo peaks in the graph field, especially the
        # strong tail echo seen on native screenshots.
        def orient_score(amps: list[int]) -> int:
            pos = max([a for a in amps if a > 0] or [0])
            tail_start = max(0, int(len(amps) * 0.78))
            tail = max([a for a in amps[tail_start:] if a > 0] or [0])
            span = max(amps) - min(amps) if amps else 0
            return pos * 4 + tail * 8 + span
        score = _score_graph_block(block) + max(orient_score(amps_n), orient_score(amps_i))
        # Bonus if this record references the same setting number.
        try:
            sn = protocol_setting_no_643(raw)
            if setting_no and sn == setting_no:
                score += 500
        except Exception:
            pass
        score += min(len(raw), 0x3A6) // 8
        return score
    except Exception:
        return -10**9


def _v16_decode_graph(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    candidates: list[tuple[str, int, bytes]] = []
    seen: set[tuple[int, int]] = set()

    def add(label: str, addr: int, raw: bytes | None) -> None:
        if not raw:
            return
        key = (int(addr or 0), len(raw))
        if key in seen:
            return
        seen.add(key)
        candidates.append((label, int(addr or 0), bytes(raw)))

    try:
        add("selected", int(self.addr), self.protocol_raw)
        add("linked", int(getattr(self, "graph_addr", 0) or 0), self.graph_raw)
        # Natural pair candidates: 4000+n <-> 6000+n.
        a = int(self.addr)
        if 4000 <= a <= 4999:
            add("pair6000", a + 2000, self._raw_for(a + 2000))
        if 6000 <= a <= 6999:
            add("pair4000", a - 2000, self._raw_for(a - 2000))
        # If selected row points to a graph address, also test its pair.
        ga = int(getattr(self, "graph_addr", 0) or 0)
        if 4000 <= ga <= 4999:
            add("graph_pair6000", ga + 2000, self._raw_for(ga + 2000))
        if 6000 <= ga <= 6999:
            add("graph_pair4000", ga - 2000, self._raw_for(ga - 2000))
        # Exhaustive loaded-record fallback by linked setting number.
        try:
            sn = int(getattr(self, "setting_no", 0) or 0)
            if sn:
                for rr in self.db.conn.execute("SELECT address, raw FROM raw_records WHERE address BETWEEN 4000 AND 6999"):
                    raw = bytes(rr["raw"] or b"")
                    try:
                        if protocol_setting_no_643(raw) == sn:
                            add("same_setting", int(rr["address"]), raw)
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass

    best = None
    best_score = -10**9
    best_label = ""
    best_addr = 0
    for label, addr, raw in candidates:
        sc = _v16_graph_score(raw, int(getattr(self, "setting_no", 0) or 0))
        if sc > best_score:
            try:
                g = decode_ascan_graph_643(raw)
                best = dict(g)
                best["source"] = label
                best["source_addr"] = addr
                best_score = sc
                best_label = label
                best_addr = addr
                self.graph_source_raw = raw
            except Exception:
                pass
    if best is not None:
        best["score"] = best_score
        best["source"] = best_label
        best["source_addr"] = best_addr
        return best
    self.graph_source_raw = self.protocol_raw or self.graph_raw or b""
    return {"error": "Нет полного блока графика 0xF4. Получите протоколы/настройки заново или перечитайте связанный 4000/6000 адрес."}


def _v16_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    """Draw graph like the native page: zones first, trace above baseline, marker.

    The native GDI path uses an upward Y axis.  Live records can encode echo as
    either sample-baseline or baseline-sample depending on source block; choose
    the orientation whose tail/overall positive echo is visible upward, then
    scale it into the fixed graph rectangle.
    """
    c = self.graph_canvas
    c.delete("all")
    native_w, native_h = 360, 230
    x0, y0 = 12, 10
    x1, y1 = x0 + native_w - 24, y0 + native_h - 34
    pw, ph = x1 - x0, y1 - y0
    baseline_y = y1 - 18
    c.create_rectangle(x0, y0, x1, y1, outline="#222")
    for i in range(1, 10):
        x = x0 + pw * i / 10.0
        c.create_line(x, y0, x, y1, fill="#cfcfcf", dash=(1, 5))
    for i in range(1, 7):
        y = y0 + ph * i / 7.0
        c.create_line(x0, y, x1, y, fill="#cfcfcf", dash=(1, 5))

    zone = _v14_zone_values(self)
    duration = max(1, int(_v16_safe_float(zone.get("duration_t10"), 7920)))

    def x_by_t10(raw_x: Any) -> float:
        rx = _v16_safe_float(raw_x, 0.0)
        return max(x0, min(x1, x0 + (rx / duration) * pw))

    def threshold_y(pct: Any) -> float:
        p = _v16_safe_float(pct, 0.0)
        return max(y0 + 4, min(y1 - 4, baseline_y - (p / 100.0) * (ph * 0.72)))

    def draw_zone(a: Any, b: Any, label: str, thr: Any = None, dash: tuple[int, int] = (3, 3)) -> None:
        aa = int(_v16_safe_float(a, 0.0)); bb = int(_v16_safe_float(b, 0.0))
        if aa <= 0 and bb <= 0:
            return
        if bb < aa:
            aa, bb = bb, aa
        xa, xb = x_by_t10(aa), x_by_t10(bb)
        if xb - xa < 2:
            xb = xa + 2
        c.create_rectangle(xa, y0 + 1, xb, y1 - 1, outline="", fill="#eeeeee", stipple="gray12")
        c.create_line(xa, y0 + 2, xa, y1 - 2, fill="#333", dash=dash, width=1)
        c.create_line(xb, y0 + 2, xb, y1 - 2, fill="#333", dash=dash, width=1)
        if thr not in (None, "", 0, "0"):
            yy = threshold_y(thr)
            c.create_line(xa, yy, xb, yy, fill="#333", dash=(2, 2), width=1)
        c.create_text((xa + xb) / 2, y0 + 9, text=label, fill="#111", font=("Arial", 8, "bold"))

    # Native order in screenshots: ВРЧ band, then ВС1/ВС2 gates.
    draw_zone(zone.get("vrch_start_raw"), zone.get("vrch_end_raw"), "ВРЧ", None, dash=(1, 4))
    draw_zone(zone.get("vs1_start_raw"), zone.get("vs1_end_raw"), "ВС1", zone.get("vs1_threshold_pct"), dash=(3, 3))
    draw_zone(zone.get("vs2_start_raw"), zone.get("vs2_end_raw"), "ВС2", zone.get("vs2_threshold_pct"), dash=(5, 2))
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")

    samples = [int(s) & 0xFF for s in (self.graph.get("samples") or [])][:GRAPH_DRAW_COUNT] if isinstance(getattr(self, "graph", None), dict) else []
    if len(samples) < 2:
        c.create_text((x0+x1)//2, (y0+y1)//2, text=(self.graph or {}).get("error", "Нет графика"), fill="#555", width=pw-10)
        return

    cand = {
        "normal": [s - GRAPH_BASELINE for s in samples],
        "inverted": [GRAPH_BASELINE - s for s in samples],
    }
    tail_start = max(0, int(len(samples) * 0.78))
    def score(amps: list[int]) -> float:
        pos = max([a for a in amps if a > 0] or [0])
        tail = max([a for a in amps[tail_start:] if a > 0] or [0])
        span = (max(amps) - min(amps)) if amps else 0
        return pos * 3 + tail * 8 + span * 0.5
    amps = cand["normal"] if score(cand["normal"]) >= score(cand["inverted"]) else cand["inverted"]
    # suppress negative dips below baseline; original page mainly displays echo envelope upward.
    posmax = max([a for a in amps if a > 0] or [1])
    gain = min(7.0, max(0.8, (ph * 0.72) / max(1, posmax)))
    pts: list[float] = []
    for i, a in enumerate(amps):
        ap = max(0, a)
        x = x0 + (i / max(1, len(amps) - 1)) * pw
        y = baseline_y - ap * gain
        y = max(y0 + 2, min(y1 - 2, y))
        pts.extend((x, y))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)

    # Marker: exact defect R/Y if available; otherwise strongest visible echo.
    mx = my = None
    try:
        r_mm = _v16_safe_float((self.defect or {}).get("defect_r"), 0.0)
        y_mm = _v16_safe_float((self.defect or {}).get("defect_y"), 0.0)
        speed = _v16_safe_float((getattr(self, "setting_params", {}) or {}).get("sound_speed"), 5900.0)
        if r_mm > 0 and speed > 0:
            mx = x_by_t10(round(r_mm * 20000.0 / speed))
            ratio = max(0.03, min(0.95, y_mm / r_mm)) if r_mm > 1 and y_mm >= 0 else 0.50
            my = y1 - 10 - ratio * (ph * 0.70)
    except Exception:
        pass
    if mx is None or my is None:
        try:
            idx, a = max(enumerate(amps), key=lambda ia: (max(0, ia[1]) + (25 if ia[0] > len(amps) * 0.80 else 0)))
            if a > 0:
                mx = x0 + (idx / max(1, len(amps) - 1)) * pw
                my = baseline_y - max(0, a) * gain
        except Exception:
            pass
    if mx is not None and my is not None:
        mx = max(x0 + 8, min(x1 - 8, float(mx)))
        my = max(y0 + 8, min(y1 - 8, float(my)))
        c.create_line(mx - 8, my, mx + 8, my, fill="#222")
        c.create_line(mx, my - 8, mx, my + 8, fill="#222")


try:
    NativeAscanProtocolSheet._decode_graph = _v16_decode_graph  # type: ignore[name-defined]
    NativeAscanProtocolSheet._draw_native_graph = _v16_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass


# Smoother sheet opening: build hidden and reveal after geometry settles.  This
# reduces the visible "jerk" when report/protocol windows render a large page.
def _v16_wrap_build_for_smooth_open(cls: Any) -> None:
    try:
        orig = cls._build
        def wrapped(self, *args, **kwargs):
            try: self.withdraw()
            except Exception: pass
            res = orig(self, *args, **kwargs)
            try: _v16_configure_sheet_buttons(self)
            except Exception: pass
            try:
                self.update_idletasks()
                self.after(80, lambda: (self.deiconify(), self.lift()))
            except Exception:
                pass
            return res
        cls._build = wrapped
    except Exception:
        pass

try:
    _v16_wrap_build_for_smooth_open(NativeReportSheet)  # type: ignore[name-defined]
    _v16_wrap_build_for_smooth_open(NativeAscanProtocolSheet)  # type: ignore[name-defined]
except Exception:
    pass


# PostgreSQL status line and password-protected settings.
def _v16_check_pg_once() -> tuple[bool, str]:
    try:
        cfg = _pg_load_config()
        conn, _driver = _pg_connect(cfg)
        try:
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
            except Exception:
                pass
        finally:
            try: conn.close()
            except Exception: pass
        return True, f"PostgreSQL: доступна"
    except Exception as exc:
        return False, f"PostgreSQL: недоступна"


def _v16_schedule_pg_check(app: Any, delay_ms: int = 500) -> None:
    def worker():
        ok, msg = _v16_check_pg_once()
        def apply():
            try:
                app.pg_status_var.set(msg)
                app.pg_lamp.configure(fg=("#0a8f08" if ok else "#b00000"))
                app.pg_lamp.configure(text="●")
            except Exception:
                pass
        try:
            app.after(0, apply)
        except Exception:
            pass
    try:
        threading.Thread(target=worker, daemon=True).start()
        app.after(30000, lambda: _v16_schedule_pg_check(app, 0))
    except Exception:
        pass


try:
    _v16_orig_build_ui = NativeLikeApp._build_ui  # type: ignore[name-defined]
    def _v16_build_ui(self: NativeLikeApp) -> None:  # type: ignore[name-defined]
        _v16_orig_build_ui(self)
        try:
            status = tk.Frame(self, bg="#efefef", bd=1, relief=tk.GROOVE)
            status.pack(side=tk.BOTTOM, fill=tk.X)
            self.pg_lamp = tk.Label(status, text="●", fg="#b00000", bg="#efefef", font=("Arial", 13, "bold"))
            self.pg_lamp.pack(side=tk.LEFT, padx=(8, 4), pady=2)
            self.pg_status_var = tk.StringVar(value="PostgreSQL: проверка...")
            tk.Label(status, textvariable=self.pg_status_var, bg="#efefef", anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            ttk.Button(status, text="Проверить БД", command=lambda: _v16_schedule_pg_check(self, 0)).pack(side=tk.RIGHT, padx=6, pady=2)
            _v16_schedule_pg_check(self, 0)
        except Exception:
            pass
    NativeLikeApp._build_ui = _v16_build_ui  # type: ignore[name-defined]
except Exception:
    pass


try:
    def _v16_pg_open_settings(self) -> None:
        try:
            from tkinter import simpledialog
            pwd = simpledialog.askstring("Доступ", "Введите пароль для настроек PostgreSQL:", show="*", parent=self)
        except Exception:
            pwd = None
        if pwd != V16_PG_SETTINGS_PASSWORD:
            if pwd is not None:
                messagebox.showerror("Доступ", "Неверный пароль", parent=self)
            return
        PostgresSettingsDialog(self)
    NativeLikeBasketExactApp.open_pg_settings = _v16_pg_open_settings  # type: ignore[name-defined]
except Exception:
    pass



# ---------------------------------------------------------------------------
# v17 runtime/graph/print pass
# ---------------------------------------------------------------------------
# Fixes reported after v16:
#   * Setting double-click: SettingDetail.PAGE_W/PAGE_H missing.
#   * Protocol double-click: fetch linked setting/graph dependencies and open the
#     protocol sheet in the same click even if selection refreshes.
#   * Protocol graph: stronger source/offset selection and orientation that keeps
#     the native tail echo peak upward; draw ВС1/ВС2/ВРЧ gates inside the graph.
#   * Print: show a preview window with printer selection / A4 PostScript save.

V17_VERSION = "v17 runtime graph print fixes"

# --- SettingDetail native-sheet crash fix ----------------------------------
try:
    SettingDetail.PAGE_W = getattr(NativeSettingSheet, "PAGE_W", 1040)  # type: ignore[name-defined]
    SettingDetail.PAGE_H = getattr(NativeSettingSheet, "PAGE_H", 1380)  # type: ignore[name-defined]
    for _name in ("_header_device_version", "_p", "_build", "_t", "_sep_title", "_row", "_draw"):
        setattr(SettingDetail, _name, getattr(NativeSettingSheet, _name))  # type: ignore[name-defined]

    def _v17_setting_detail_init(self: SettingDetail, master: tk.Misc, row: sqlite3.Row, raw: bytes):  # type: ignore[name-defined]
        tk.Toplevel.__init__(self, master)
        self.master_app = master
        self.row = row
        self.raw = bytes(raw or b"")
        try:
            self.addr = int(row["address"])
        except Exception:
            self.addr = 0
        try:
            self.params = decode_nastr2_params_643(self.raw, self.addr)
        except Exception as exc:
            self.params = {"error": str(exc)}
        self.title("Настройка")
        self.geometry("1080x900")
        self.minsize(920, 680)
        self.withdraw()
        self._build()
        try:
            _v17_configure_sheet_buttons(self)  # defined below; safe at runtime
        except Exception:
            pass
        self.update_idletasks()
        self.after(60, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    SettingDetail.__init__ = _v17_setting_detail_init  # type: ignore[name-defined]
except Exception:
    pass


# --- Protocol dependency open: one double-click must fetch and open ----------
def _v17_open_protocol_sheet_after_dependencies(app: Any, addr: int) -> None:
    """Fetch linked setting/graph if needed and open sheet immediately.

    Older wrappers fetched a setting and then reloaded the Treeview; selection could
    be lost, forcing the user to double-click a second time.  This routine keeps the
    selected address in a local variable and opens the protocol sheet directly.
    """
    try:
        _v10_ensure_protocol_dependencies(app, int(addr))  # type: ignore[name-defined]
    except Exception as exc:
        try:
            app.status_var.set(f"Не удалось предварительно получить настройку/график: {exc}")
        except Exception:
            pass
    try:
        row = app.db.row_by_addr("protocols", int(addr))
        if not row:
            raw_row = app.db.get_raw_by_addr(int(addr))
            if raw_row:
                raw = bytes(raw_row["raw"])
                fields = decode_protocol_ascan_643(raw, int(addr), None, strict=False)
                app.db.save_protocol(int(raw_row["id"]), int(addr), fields)
                row = app.db.row_by_addr("protocols", int(addr))
        if not row:
            messagebox.showinfo("Данные", "Протокол ещё не получен/не дешифрован. Нажмите получение данных.", parent=app)
            return
        NativeAscanProtocolSheet(app, app.db, int(addr))  # type: ignore[name-defined]
    except Exception as exc:
        messagebox.showerror("Протокол А-развертки", str(exc), parent=app)

try:
    _v17_prev_open_selected_detail = NativeLikeBasketExactApp.open_selected_detail  # type: ignore[name-defined]
    def _v17_open_selected_detail(self, forced_bucket: Optional[str] = None):
        addr = self.selected_addr()
        if addr is not None and kind_for_addr(int(addr)) in ("protocol_short", "protocol_graph", "bscan"):
            _v17_open_protocol_sheet_after_dependencies(self, int(addr))
            return
        return _v17_prev_open_selected_detail(self, forced_bucket)
    NativeLikeBasketExactApp.open_selected_detail = _v17_open_selected_detail  # type: ignore[name-defined]
except Exception:
    pass


# --- Graph source/offset/orientation ---------------------------------------
def _v17_percentile(vals: list[float], q: float, default: float = 0.0) -> float:
    if not vals:
        return default
    vals = sorted(vals)
    idx = min(len(vals) - 1, max(0, int(round((len(vals) - 1) * q))))
    return float(vals[idx])


def _v17_orientation_score(samples: list[int], inverted: bool) -> float:
    if not samples:
        return -1e9
    if inverted:
        amps = [GRAPH_BASELINE - int(s) for s in samples]
    else:
        amps = [int(s) - GRAPH_BASELINE for s in samples]
    positives = [a for a in amps if a > 0]
    posmax = max(positives or [0])
    tail_start = max(0, int(len(amps) * 0.76))
    head_end = max(1, int(len(amps) * 0.16))
    tail = max([a for a in amps[tail_start:] if a > 0] or [0])
    head = max([a for a in amps[:head_end] if a > 0] or [0])
    span = max(amps) - min(amps) if amps else 0
    # Native screenshots show a strong right/tail echo.  Prefer the orientation
    # that makes the tail echo positive/upward, but still keep head/overall peaks.
    return tail * 30.0 + head * 8.0 + posmax * 5.0 + span * 0.8 + len(set(samples))


def _v17_block_score(raw: bytes, off: int, setting_no: int = 0) -> float:
    if off < 0 or off + GRAPH_COPY_LEN > len(raw):
        return -1e9
    block = raw[off:off + GRAPH_COPY_LEN]
    if len(block) < GRAPH_DRAW_COUNT:
        return -1e9
    samples = [int(b) for b in block[:GRAPH_DRAW_COUNT]]
    uniq = len(set(samples))
    if uniq < 5:
        return -1e9
    pad = sum(1 for b in samples if b in (0, 0xFF))
    near = sum(1 for b in samples if 0x20 <= b <= 0xF0)
    orient = max(_v17_orientation_score(samples, False), _v17_orientation_score(samples, True))
    score = orient + uniq * 2.0 + near * 0.2 - pad * 4.0
    try:
        sn = protocol_setting_no_643(raw)
        if setting_no and sn == setting_no:
            score += 250.0
    except Exception:
        pass
    return score


def _v17_graph_offsets(raw: bytes) -> list[int]:
    if not raw or len(raw) < GRAPH_COPY_LEN:
        return []
    candidates = [len(raw) - GRAPH_COPY_LEN]
    for off in (GRAPH_OFF, 0x1B8, 0x1C2, 0x1C5, 0x1D5, 0x1E5, 0x150, 0x160):
        if 0 <= off <= len(raw) - GRAPH_COPY_LEN:
            candidates.append(off)
    # Full scan catches shifted RESULTS2 layouts without relying on old guesses.
    if len(raw) <= 0x1000:
        step = 1
        best_scan: list[tuple[float, int]] = []
        for off in range(0, len(raw) - GRAPH_COPY_LEN + 1, step):
            s = _v17_block_score(raw, off)
            if s > -1e8:
                best_scan.append((s, off))
        best_scan.sort(reverse=True)
        candidates.extend(off for _s, off in best_scan[:16])
    seen: set[int] = set(); out: list[int] = []
    for off in candidates:
        if off not in seen and 0 <= off <= len(raw) - GRAPH_COPY_LEN:
            seen.add(off); out.append(off)
    return out


def _v17_decode_graph_from_raw(raw: bytes, setting_no: int = 0) -> dict[str, Any]:
    best: Optional[dict[str, Any]] = None
    best_score = -1e9
    for off in _v17_graph_offsets(raw):
        score = _v17_block_score(raw, off, setting_no)
        if score <= best_score:
            continue
        block = list(raw[off:off + GRAPH_COPY_LEN])
        samples = [int(b) for b in block[:GRAPH_DRAW_COUNT]]
        inv_score = _v17_orientation_score(samples, True)
        norm_score = _v17_orientation_score(samples, False)
        inverted = bool(inv_score > norm_score)
        best_score = score
        best = {
            "offset": off,
            "copy_len": GRAPH_COPY_LEN,
            "draw_count": len(samples),
            "baseline": GRAPH_BASELINE,
            "raw_block": block,
            "samples": samples,
            "orientation": "baseline_minus_sample" if inverted else "sample_minus_baseline",
            "score": score,
            "min_sample": min(samples) if samples else None,
            "max_sample": max(samples) if samples else None,
        }
    if best is None:
        raise ValueError("Нет полного блока графика 0xF4")
    return best


def _v17_decode_graph(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    setting_no = 0
    try:
        setting_no = int((getattr(self, "setting_params", {}) or {}).get("setting_no") or 0)
    except Exception:
        pass
    candidates: list[tuple[str, int, bytes]] = []
    seen: set[tuple[int, int, bytes]] = set()
    def add(label: str, addr: int, raw: bytes | None) -> None:
        if not raw or len(raw) < GRAPH_COPY_LEN:
            return
        # Skip short 0x56 report/diagnostic frames.
        if len(raw) <= 0x90:
            return
        key = (int(addr or 0), len(raw), bytes(raw[:8]))
        if key in seen:
            return
        seen.add(key)
        candidates.append((label, int(addr or 0), bytes(raw)))
    try:
        add("selected", int(self.addr), self.protocol_raw)
        add("linked", int(getattr(self, "graph_addr", 0) or 0), self.graph_raw)
        a = int(self.addr)
        if 4000 <= a <= 4999:
            add("pair6000", a + 2000, self._raw_for(a + 2000))
        if 6000 <= a <= 6999:
            add("pair4000", a - 2000, self._raw_for(a - 2000))
        ga = int(getattr(self, "graph_addr", 0) or 0)
        if 4000 <= ga <= 4999:
            add("graph_pair6000", ga + 2000, self._raw_for(ga + 2000))
        if 6000 <= ga <= 6999:
            add("graph_pair4000", ga - 2000, self._raw_for(ga - 2000))
        # All already loaded RESULTS2 records with the same setting number.
        for rr in self.db.conn.execute("SELECT address, raw FROM raw_records WHERE address BETWEEN 4000 AND 6999"):
            raw = bytes(rr["raw"])
            if len(raw) <= 0x90:
                continue
            if setting_no:
                try:
                    if protocol_setting_no_643(raw) != setting_no:
                        continue
                except Exception:
                    pass
            add("loaded", int(rr["address"]), raw)
    except Exception:
        pass
    best = None; best_score = -1e9; best_label = ""; best_addr = 0; best_raw = b""
    for label, addr, raw in candidates:
        try:
            g = _v17_decode_graph_from_raw(raw, setting_no)
            score = float(g.get("score") or 0.0)
            if label in ("selected", "graph_pair4000", "pair4000"):
                score += 80.0
            if score > best_score:
                best_score = score; best = g; best_label = label; best_addr = addr; best_raw = raw
        except Exception:
            continue
    if best is not None:
        best["source"] = best_label
        best["source_addr"] = best_addr
        self.graph_source_raw = best_raw
        return best
    self.graph_source_raw = self.protocol_raw or self.graph_raw or b""
    return {"error": "Нет полного блока графика 0xF4. Получите протоколы и связанный 4000/6000 адрес заново."}


def _v17_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    c = self.graph_canvas
    c.delete("all")
    w, h = 360, 230
    x0, y0 = 12, 10
    x1, y1 = w - 14, h - 30
    pw, ph = x1 - x0, y1 - y0
    baseline_y = y1 - 18
    c.create_rectangle(x0, y0, x1, y1, outline="#222")
    for i in range(1, 10):
        x = x0 + pw * i / 10.0
        c.create_line(x, y0, x, y1, fill="#cfcfcf", dash=(1, 5))
    for i in range(1, 7):
        y = y0 + ph * i / 7.0
        c.create_line(x0, y, x1, y, fill="#cfcfcf", dash=(1, 5))

    zone = _v14_zone_values(self)  # type: ignore[name-defined]
    duration = int(_v16_safe_float(zone.get("duration_t10"), 7920)) or 7920
    def x_by_t10(v: Any) -> float:
        rx = max(0.0, _v16_safe_float(v, 0.0))
        return max(x0, min(x1, x0 + (rx / max(1, duration)) * pw))
    def draw_gate(a: Any, b: Any, label: str, dash: tuple[int, int], y_label: int) -> None:
        aa = _v16_safe_float(a, 0.0); bb = _v16_safe_float(b, 0.0)
        if aa <= 0 and bb <= 0:
            return
        if bb < aa:
            aa, bb = bb, aa
        xa, xb = x_by_t10(aa), x_by_t10(bb)
        if xb - xa < 2:
            xb = xa + 2
        c.create_line(xa, y0 + 2, xa, y1 - 2, fill="#222", dash=dash, width=1)
        c.create_line(xb, y0 + 2, xb, y1 - 2, fill="#222", dash=dash, width=1)
        c.create_text((xa + xb) / 2, y0 + y_label, text=label, fill="#111", font=("Arial", 8, "bold"))
    draw_gate(zone.get("vrch_start_raw"), zone.get("vrch_end_raw"), "ВРЧ", (1, 4), 10)
    draw_gate(zone.get("vs1_start_raw"), zone.get("vs1_end_raw"), "ВС1", (3, 3), 24)
    draw_gate(zone.get("vs2_start_raw"), zone.get("vs2_end_raw"), "ВС2", (5, 2), 10)
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")

    samples = [int(s) & 0xFF for s in ((self.graph or {}).get("samples") or [])][:GRAPH_DRAW_COUNT]
    if len(samples) < 2:
        c.create_text((x0+x1)/2, (y0+y1)/2, text=(self.graph or {}).get("error", "Нет графика"), fill="#555", width=pw-10)
        return
    inv = (self.graph or {}).get("orientation") == "baseline_minus_sample"
    if inv:
        amps = [GRAPH_BASELINE - s for s in samples]
    else:
        amps = [s - GRAPH_BASELINE for s in samples]
    # If the chosen orientation still puts the tail echo below baseline, flip it.
    tail_start = max(0, int(len(samples) * 0.76))
    tail_pos = max([a for a in amps[tail_start:] if a > 0] or [0])
    alt = [GRAPH_BASELINE - s for s in samples] if not inv else [s - GRAPH_BASELINE for s in samples]
    alt_tail = max([a for a in alt[tail_start:] if a > 0] or [0])
    if alt_tail > tail_pos + 4:
        amps = alt
    positives = [a for a in amps if a > 0]
    if not positives:
        positives = [abs(a) for a in amps]
        amps = [abs(a) for a in amps]
    p98 = max(1.0, _v17_percentile([float(a) for a in positives], 0.98, max(positives or [1])))
    gain = min(8.0, max(0.55, (ph * 0.72) / p98))
    pts: list[float] = []
    for i, a in enumerate(amps):
        ap = max(0.0, float(a))
        x = x0 + (i / max(1, len(amps) - 1)) * pw
        y = baseline_y - ap * gain
        y = max(y0 + 2, min(y1 - 2, y))
        pts.extend((x, y))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)
    # Marker: use exact defect if present, else strongest positive echo, with a
    # bonus to the final part of the trace so the tail peak is marked like native.
    mx = my = None
    try:
        r_mm = _v16_safe_float((self.defect or {}).get("defect_r"), 0.0)
        if r_mm > 0:
            speed = _v16_safe_float((getattr(self, "setting_params", {}) or {}).get("sound_speed"), 5900.0)
            mx = x_by_t10(round(r_mm * 20000.0 / max(1.0, speed)))
            y_mm = _v16_safe_float((self.defect or {}).get("defect_y"), 0.0)
            ratio = max(0.05, min(0.95, y_mm / r_mm)) if r_mm > 1 and y_mm >= 0 else 0.50
            my = y1 - 10 - ratio * (ph * 0.70)
    except Exception:
        pass
    if mx is None or my is None:
        try:
            idx, a = max(enumerate(amps), key=lambda ia: max(0.0, ia[1]) + (30 if ia[0] >= tail_start else 0))
            mx = x0 + (idx / max(1, len(amps) - 1)) * pw
            my = baseline_y - max(0.0, float(a)) * gain
        except Exception:
            pass
    if mx is not None and my is not None:
        mx = max(x0 + 8, min(x1 - 8, float(mx)))
        my = max(y0 + 8, min(y1 - 8, float(my)))
        c.create_line(mx - 8, my, mx + 8, my, fill="#222")
        c.create_line(mx, my - 8, mx, my + 8, fill="#222")

try:
    NativeAscanProtocolSheet._decode_graph = _v17_decode_graph  # type: ignore[name-defined]
    NativeAscanProtocolSheet._draw_native_graph = _v17_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass


# --- Print preview with printer selection ----------------------------------
def _v17_enum_printers() -> list[str]:
    if os.name != "nt":
        return []
    try:
        import win32print  # type: ignore
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return [p[2] for p in win32print.EnumPrinters(flags) if len(p) > 2 and p[2]]
    except Exception:
        return []


def _v17_default_printer() -> str:
    if os.name != "nt":
        return ""
    try:
        import win32print  # type: ignore
        return win32print.GetDefaultPrinter() or ""
    except Exception:
        return ""


def _v17_clone_canvas_items(src: tk.Canvas, dst: tk.Canvas, scale: float = 0.55, ox: float = 0.0, oy: float = 0.0) -> None:
    def sc(vals: list[float]) -> list[float]:
        out: list[float] = []
        for i, v in enumerate(vals):
            out.append(ox + v * scale if i % 2 == 0 else oy + v * scale)
        return out
    for item in src.find_all():
        try:
            typ = src.type(item)
            coords = [float(v) for v in src.coords(item)]
            if typ == "line":
                dst.create_line(*sc(coords), fill=src.itemcget(item, "fill") or "#111", dash=src.itemcget(item, "dash"), width=max(1, int(float(src.itemcget(item, "width") or 1) * scale)))
            elif typ == "rectangle":
                dst.create_rectangle(*sc(coords), outline=src.itemcget(item, "outline") or "#111", fill=src.itemcget(item, "fill") or "")
            elif typ == "text":
                txt = src.itemcget(item, "text")
                font = src.itemcget(item, "font") or "Arial 9"
                anchor = src.itemcget(item, "anchor") or "nw"
                width_s = src.itemcget(item, "width")
                opts: dict[str, Any] = {"text": txt, "fill": src.itemcget(item, "fill") or "#111", "anchor": anchor, "font": font}
                try:
                    if width_s and float(width_s) > 0:
                        opts["width"] = int(float(width_s) * scale)
                except Exception:
                    pass
                xy = sc(coords[:2])
                dst.create_text(xy[0], xy[1], **opts)
            elif typ == "window":
                # Protocol graph is an embedded Canvas; clone its primitive items into preview.
                win_name = src.itemcget(item, "window")
                if win_name:
                    try:
                        child = src.nametowidget(win_name)
                        if isinstance(child, tk.Canvas) and coords:
                            _v17_clone_canvas_items(child, dst, scale, ox + coords[0] * scale, oy + coords[1] * scale)
                    except Exception:
                        pass
        except Exception:
            continue


def _v17_save_postscript(canvas: tk.Canvas, path: str) -> None:
    canvas.update_idletasks()
    canvas.postscript(file=path, colormode="gray", pagewidth="210m", pageheight="297m", rotate=False)


def _v17_print_file_to_printer(path: str, printer: str = "") -> None:
    if os.name == "nt":
        try:
            import win32api  # type: ignore
            if printer:
                win32api.ShellExecute(0, "printto", path, f'"{printer}"', ".", 0)
            else:
                win32api.ShellExecute(0, "print", path, None, ".", 0)
            return
        except Exception:
            try:
                if printer:
                    os.startfile(path, "print")  # type: ignore[attr-defined]
                else:
                    os.startfile(path, "print")  # type: ignore[attr-defined]
                return
            except Exception:
                pass
    raise RuntimeError("Автопечать недоступна. Сохраните .ps и распечатайте из просмотрщика.")


def _v17_print_preview(owner: tk.Misc, canvas: Optional[tk.Canvas] = None, title: str = "peleng_sheet") -> None:
    try:
        if canvas is None:
            canvas = getattr(owner, "page_canvas", None)
        if not isinstance(canvas, tk.Canvas):
            messagebox.showerror("Печать", "Не найден Canvas листа для печати", parent=owner)
            return
        win = tk.Toplevel(owner)
        win.title("Предпросмотр печати A4")
        win.geometry("760x920")
        top = ttk.Frame(win, padding=6)
        top.pack(fill=tk.X)
        printers = _v17_enum_printers()
        default_prn = _v17_default_printer()
        ttk.Label(top, text="Принтер:").pack(side=tk.LEFT, padx=(0, 4))
        prn_var = tk.StringVar(value=default_prn or (printers[0] if printers else ""))
        combo = ttk.Combobox(top, textvariable=prn_var, values=printers, width=42, state=("readonly" if printers else "normal"))
        combo.pack(side=tk.LEFT, padx=4)
        body = tk.Canvas(win, bg="#555", highlightthickness=0)
        vsb = ttk.Scrollbar(win, orient=tk.VERTICAL, command=body.yview)
        body.configure(yscrollcommand=vsb.set)
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        scale = 0.55
        try:
            w = int(float(canvas.cget("width")))
            h = int(float(canvas.cget("height")))
        except Exception:
            w, h = 1040, 1380
        page = tk.Canvas(body, bg="white", width=int(w*scale), height=int(h*scale), bd=1, relief=tk.SOLID, highlightthickness=0)
        body.create_window(14, 14, anchor="nw", window=page)
        body.configure(scrollregion=(0, 0, int(w*scale)+28, int(h*scale)+28))
        _v17_clone_canvas_items(canvas, page, scale)
        safe_title = re.sub(r"[^A-Za-z0-9А-Яа-я_.-]+", "_", str(title or "peleng_sheet"))[:80]
        def save_as() -> Optional[str]:
            path = filedialog.asksaveasfilename(parent=win, title="Сохранить A4 PostScript", defaultextension=".ps", initialfile=f"{safe_title}.ps", filetypes=[("PostScript", "*.ps"), ("Все файлы", "*.*")])
            if not path:
                return None
            _v17_save_postscript(canvas, path)
            messagebox.showinfo("Печать", f"Лист сохранён:\n{path}", parent=win)
            return path
        def do_print() -> None:
            import tempfile
            path = os.path.join(tempfile.gettempdir(), f"{safe_title}.ps")
            _v17_save_postscript(canvas, path)
            try:
                _v17_print_file_to_printer(path, prn_var.get().strip())
                messagebox.showinfo("Печать", "Задание отправлено в печать", parent=win)
            except Exception as exc:
                messagebox.showwarning("Печать", f"Не удалось открыть системную печать:\n{exc}\n\nФайл сохранён:\n{path}", parent=win)
        ttk.Button(top, text="Печать", command=do_print).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Сохранить A4", command=save_as).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Закрыть", command=win.destroy).pack(side=tk.RIGHT, padx=4)
    except Exception as exc:
        messagebox.showerror("Печать", str(exc), parent=owner)


def _v17_configure_sheet_buttons(win: tk.Misc) -> None:
    def walk(w: tk.Misc):
        yield w
        try:
            for ch in w.winfo_children():
                yield from walk(ch)
        except Exception:
            return
    for w in walk(win):
        try:
            txt = str(w.cget("text"))
        except Exception:
            continue
        if txt in ("Печать", "Сохранить"):
            try:
                if txt == "Печать":
                    w.configure(command=lambda _w=win: _v17_print_preview(_w, getattr(_w, "page_canvas", None), _w.title()))
                else:
                    w.configure(command=lambda _w=win: _v17_print_preview(_w, getattr(_w, "page_canvas", None), _w.title()))
            except Exception:
                pass

# Re-wrap existing sheet build methods so v17 print buttons replace v16 PS-only handler.
def _v17_wrap_buttons(cls: Any) -> None:
    try:
        orig = cls._build
        def wrapped(self, *args, **kwargs):
            res = orig(self, *args, **kwargs)
            try:
                self.after(90, lambda: _v17_configure_sheet_buttons(self))
            except Exception:
                pass
            return res
        cls._build = wrapped
    except Exception:
        pass
try:
    _v17_wrap_buttons(NativeReportSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(NativeAscanProtocolSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(SettingDetail)  # type: ignore[name-defined]
except Exception:
    pass



# ---------------------------------------------------------------------------
# v18 runtime fixes: safe_i8, graph fetch/orientation, A4 print preview, compact settings
# ---------------------------------------------------------------------------
V18_VERSION = "v18 final print/graph/runtime fixes"

# Some v13/v17 patches used signed-byte helper from reverse notes, but the
# generated runtime file did not define it.  Keep it global for decode_defect_643.
def safe_i8(buf: bytes, off: int, default: int = 0) -> int:
    try:
        if off < 0 or off >= len(buf):
            return int(default)
        v = int(buf[off]) & 0xFF
        return v - 256 if v >= 128 else v
    except Exception:
        return int(default)

# Make the setting sheet a bit more printable/compact.  Coordinates remain the
# native-like layout, but the page is already A4-proportional for preview/print.
try:
    NativeSettingSheet.PAGE_W = 980  # type: ignore[name-defined]
    NativeSettingSheet.PAGE_H = 1320  # type: ignore[name-defined]
    SettingDetail.PAGE_W = NativeSettingSheet.PAGE_W  # type: ignore[name-defined]
    SettingDetail.PAGE_H = NativeSettingSheet.PAGE_H  # type: ignore[name-defined]
except Exception:
    pass


def _v18_raw_is_full_graph(raw: bytes | None) -> bool:
    if not raw or len(raw) < GRAPH_COPY_LEN:
        return False
    if len(raw) <= 0x90:
        return False
    try:
        g = _v17_decode_graph_from_raw(bytes(raw), 0)  # type: ignore[name-defined]
        return bool(g.get("samples"))
    except Exception:
        try:
            decode_ascan_graph_643(bytes(raw))
            return True
        except Exception:
            return False


def _v18_protocol_candidate_addrs(addr: int, row: Any = None) -> list[int]:
    out: list[int] = []
    def add(a: Any) -> None:
        try:
            ia = int(a)
        except Exception:
            return
        if ia and ia not in out:
            out.append(ia)
    add(addr)
    try:
        if row and str(row["GRAPH_ADDR"] or "").isdigit():
            add(int(row["GRAPH_ADDR"]))
    except Exception:
        pass
    # Natural 4000/6000 pair.  Native often shows the protocol row in one range
    # while graph samples are in the paired record.
    if 4000 <= int(addr) <= 4999:
        add(int(addr) + 2000)
    if 6000 <= int(addr) <= 6999:
        add(int(addr) - 2000)
    # Same low id in both ranges, even if addr is stale/mapped.
    low = int(addr) % 1000
    if low:
        add(4000 + low)
        add(6000 + low)
    return out


def _v18_ensure_protocol_dependencies(app: Any, addr: int) -> None:
    """Fetch setting and graph candidates in one double-click, then open sheet."""
    addr = int(addr)
    # First setting: native sheet needs linked NASTR2 immediately.
    try:
        setting_addr = _v12_protocol_setting_addr(app.db, addr)  # type: ignore[name-defined]
    except Exception:
        try:
            setting_addr, _ga = _v10_protocol_dependency_addrs(app.db, addr)  # type: ignore[name-defined]
        except Exception:
            setting_addr = 0
    if setting_addr:
        rr = app.db.get_raw_by_addr(setting_addr)
        raw = bytes(rr["raw"]) if rr else None
        if not _v10_setting_raw_is_good(raw, setting_addr):  # type: ignore[name-defined]
            _v10_fetch_addr_safely(app, setting_addr, "настройку протокола")  # type: ignore[name-defined]
            rr = app.db.get_raw_by_addr(setting_addr)
            raw = bytes(rr["raw"]) if rr else None
        if raw:
            try:
                fields, params = decode_setting_643(raw, setting_addr, app.device_no, strict=False)
                app.db.save_setting(int(rr["id"]) if rr else 0, setting_addr, fields, params)
            except Exception:
                pass
    # Then graph.  Fetch all plausible candidates which are absent or short.  It
    # is only a few addresses and avoids the "double click twice" workflow.
    row = app.db.row_by_addr("protocols", addr)
    for a in _v18_protocol_candidate_addrs(addr, row):
        rr = app.db.get_raw_by_addr(a)
        raw = bytes(rr["raw"]) if rr else None
        if a != addr and not _v18_raw_is_full_graph(raw):
            _v10_fetch_addr_safely(app, a, "запись графика/протокола")  # type: ignore[name-defined]
    try:
        app.reload_idx_tables()
    except Exception:
        pass


def _v18_open_protocol_sheet_after_dependencies(app: Any, addr: int) -> None:
    try:
        _v18_ensure_protocol_dependencies(app, int(addr))
    except Exception as exc:
        try:
            app.status_var.set(f"Не удалось предварительно получить настройку/график: {exc}")
        except Exception:
            pass
    try:
        row = app.db.row_by_addr("protocols", int(addr))
        if not row:
            raw_row = app.db.get_raw_by_addr(int(addr))
            if raw_row:
                raw = bytes(raw_row["raw"])
                fields = decode_protocol_ascan_643(raw, int(addr), None, strict=False)
                app.db.save_protocol(int(raw_row["id"]), int(addr), fields)
                row = app.db.row_by_addr("protocols", int(addr))
        if not row:
            messagebox.showinfo("Данные", "Протокол ещё не получен/не дешифрован. Нажмите получение отчёта.", parent=app)
            return
        NativeAscanProtocolSheet(app, app.db, int(addr))  # type: ignore[name-defined]
    except Exception as exc:
        messagebox.showerror("Протокол А-развертки", str(exc), parent=app)

try:
    def _v18_open_selected_detail(self, forced_bucket: Optional[str] = None):
        addr = self.selected_addr()
        if addr is not None and kind_for_addr(int(addr)) in ("protocol_short", "protocol_graph", "bscan"):
            _v18_open_protocol_sheet_after_dependencies(self, int(addr))
            return
        return _v17_prev_open_selected_detail(self, forced_bucket)  # type: ignore[name-defined]
    NativeLikeBasketExactApp.open_selected_detail = _v18_open_selected_detail  # type: ignore[name-defined]
except Exception:
    pass


# Force graph orientation to native screen sense: raw echo is drawn upward.  This
# uses baseline-sample for the live devices where the previous build put the tail
# echo downward.  Negative dips are suppressed to the baseline like the native
# printout view, so the end spike is visible upward.
def _v18_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    c = self.graph_canvas
    c.delete("all")
    w, h = 360, 230
    x0, y0 = 12, 10
    x1, y1 = w - 14, h - 30
    pw, ph = x1 - x0, y1 - y0
    baseline_y = y1 - 18
    c.create_rectangle(x0, y0, x1, y1, outline="#222")
    for i in range(1, 10):
        x = x0 + pw * i / 10.0
        c.create_line(x, y0, x, y1, fill="#cfcfcf", dash=(1, 5))
    for i in range(1, 7):
        y = y0 + ph * i / 7.0
        c.create_line(x0, y, x1, y, fill="#cfcfcf", dash=(1, 5))

    zone = _v14_zone_values(self)  # type: ignore[name-defined]
    duration = int(_v16_safe_float(zone.get("duration_t10"), 7920)) or 7920  # type: ignore[name-defined]
    def x_by_t10(v: Any) -> float:
        rx = max(0.0, _v16_safe_float(v, 0.0))  # type: ignore[name-defined]
        return max(x0, min(x1, x0 + (rx / max(1, duration)) * pw))
    def draw_gate(a: Any, b: Any, label: str, dash: tuple[int, int], y_label: int) -> None:
        aa = _v16_safe_float(a, 0.0); bb = _v16_safe_float(b, 0.0)  # type: ignore[name-defined]
        if aa <= 0 and bb <= 0:
            return
        if bb < aa:
            aa, bb = bb, aa
        xa, xb = x_by_t10(aa), x_by_t10(bb)
        if xb - xa < 2:
            xb = xa + 2
        c.create_line(xa, y0 + 2, xa, y1 - 2, fill="#222", dash=dash, width=1)
        c.create_line(xb, y0 + 2, xb, y1 - 2, fill="#222", dash=dash, width=1)
        c.create_text((xa + xb) / 2, y0 + y_label, text=label, fill="#111", font=("Arial", 8, "bold"))
    draw_gate(zone.get("vrch_start_raw"), zone.get("vrch_end_raw"), "ВРЧ", (1, 4), 10)
    draw_gate(zone.get("vs1_start_raw"), zone.get("vs1_end_raw"), "ВС1", (3, 3), 24)
    draw_gate(zone.get("vs2_start_raw"), zone.get("vs2_end_raw"), "ВС2", (5, 2), 10)
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")

    samples = [int(s) & 0xFF for s in ((self.graph or {}).get("samples") or [])][:GRAPH_DRAW_COUNT]
    if len(samples) < 2:
        c.create_text((x0+x1)/2, (y0+y1)/2, text=(self.graph or {}).get("error", "Нет графика"), fill="#555", width=pw-10)
        return
    amps = [GRAPH_BASELINE - s for s in samples]
    # Suppress downward dips.  Native printed view emphasizes the envelope above baseline.
    positives = [max(0, int(a)) for a in amps]
    if max(positives or [0]) < 3:
        # Fallback for rare opposite-polarity records.
        positives = [max(0, int(s - GRAPH_BASELINE)) for s in samples]
    p98 = max(1.0, _v17_percentile([float(a) for a in positives if a > 0], 0.98, max(positives or [1])))  # type: ignore[name-defined]
    gain = min(10.0, max(0.55, (ph * 0.72) / p98))
    pts: list[float] = []
    for i, ap in enumerate(positives):
        x = x0 + (i / max(1, len(positives) - 1)) * pw
        y = baseline_y - float(ap) * gain
        y = max(y0 + 2, min(y1 - 2, y))
        pts.extend((x, y))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)
    # marker: exact R/Y if present, otherwise strongest visible tail-weighted echo
    mx = my = None
    try:
        r_mm = _v16_safe_float((self.defect or {}).get("defect_r"), 0.0)  # type: ignore[name-defined]
        if r_mm > 0:
            speed = _v16_safe_float((getattr(self, "setting_params", {}) or {}).get("sound_speed"), 5900.0)  # type: ignore[name-defined]
            mx = x_by_t10(round(r_mm * 20000.0 / max(1.0, speed)))
            y_mm = _v16_safe_float((self.defect or {}).get("defect_y"), 0.0)  # type: ignore[name-defined]
            ratio = max(0.05, min(0.95, y_mm / r_mm)) if r_mm > 1 and y_mm >= 0 else 0.50
            my = y1 - 10 - ratio * (ph * 0.70)
    except Exception:
        pass
    if mx is None or my is None:
        tail_start = max(0, int(len(positives) * 0.70))
        idx, a = max(enumerate(positives), key=lambda ia: ia[1] + (25 if ia[0] >= tail_start else 0))
        mx = x0 + (idx / max(1, len(positives) - 1)) * pw
        my = baseline_y - float(a) * gain
    mx = max(x0 + 8, min(x1 - 8, float(mx)))
    my = max(y0 + 8, min(y1 - 8, float(my)))
    c.create_line(mx - 8, my, mx + 8, my, fill="#222")
    c.create_line(mx, my - 8, mx, my + 8, fill="#222")

try:
    NativeAscanProtocolSheet._draw_native_graph = _v18_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass


# Print preview without a separate "Сохранить A4" button.  If a legacy report
# sheet is Frame-based and has no page_canvas, generate a temporary A4 Canvas
# from its decoded rows so printing does not fail with "Не найден Canvas".
def _v18_make_report_print_canvas(owner: Any) -> Optional[tk.Canvas]:
    try:
        rows = owner._rows_for_group()
    except Exception:
        return None
    c = tk.Canvas(owner, bg="white", width=1040, height=1380, highlightthickness=0)
    # Keep it unmapped; Canvas can still be postscripted/cloned.
    try:
        first = rows[0] if rows else None
        vals0 = _native_report_detail_values(owner.db, first) if first else {}
        device = str(first["NUMPRIB"] if first and "NUMPRIB" in first.keys() else "")
        version = str(first["NUMVERS"] if first and "NUMVERS" in first.keys() else "")
        c.create_text(60, 50, text=f"ОТЧЕТ № {getattr(owner, 'group_base', 0) % 10000 // 100 if getattr(owner, 'group_base', 0) else ''}", anchor="nw", font=("Arial", 11, "bold"))
        c.create_text(60, 78, text=f"о контроле дефектоскопом УД2-102 № {device}, Версия {version}", anchor="nw", font=("Arial", 9))
        operator_code = str(first["KODOPERA"] if first else "")
        operator_name = _operator_name_for_code(operator_code)
        lines = [("Предприятие", _report_enterprise()), ("Подразделение", _report_subdivision()), ("Оператор: шифр", operator_code), ("Фамилия", operator_name), ("НТД на контроль", "СТО РЖД 1.11.002-2008 (ТИ 07.73-2009)"), ("Номер настройки", str(vals0.get("setting_no", "")))]
        y = 135
        for k, v in lines:
            c.create_text(60, y, text=k, anchor="nw", font=("Arial", 9))
            c.create_text(230, y, text=str(v), anchor="nw", font=("Arial", 10, "bold" if k in ("Предприятие","Подразделение","Фамилия","НТД на контроль") else "normal"))
            y += 24
        cols = ["№", "Дата", "Объект: тип", "Номер объекта", "Плавка", "З-д", "Год", "Стор", "шейка", "обод", "обт. колес", "нал. гребня", "к-во деф"]
        widths = [38, 86, 150, 120, 80, 55, 55, 55, 95, 90, 90, 90, 65]
        x0, y0 = 60, 310
        x = x0
        for title, ww in zip(cols, widths):
            c.create_rectangle(x, y0, x+ww, y0+24, outline="#111", fill="#eee")
            c.create_text(x+3, y0+4, text=title, anchor="nw", font=("Arial", 7, "bold"), width=ww-6)
            x += ww
        for i, row in enumerate(rows[:48], 1):
            vals = _native_report_detail_values(owner.db, row)
            line = [str(i), _native_report_display_date(vals["date"]), vals["obj_type"], vals["numobj"], vals["smelting"], vals["factory"], vals["year"], vals["side"], vals["neck"], vals["rim"], vals["wheel_turn"], vals["crest"], vals["defects"]]
            x = x0; yy = y0 + 24*i
            for val, ww in zip(line, widths):
                c.create_rectangle(x, yy, x+ww, yy+22, outline="#111")
                c.create_text(x+3, yy+4, text=str(val), anchor="nw", font=("Arial", 7), width=ww-6)
                x += ww
        c.create_text(520, 1300, text="Подпись:", anchor="center", font=("Arial", 9))
        owner.page_canvas = c
        return c
    except Exception:
        try:
            c.destroy()
        except Exception:
            pass
        return None


def _v18_print_preview(owner: tk.Misc, canvas: Optional[tk.Canvas] = None, title: str = "peleng_sheet") -> None:
    try:
        if canvas is None:
            canvas = getattr(owner, "page_canvas", None)
        if not isinstance(canvas, tk.Canvas):
            canvas = _v18_make_report_print_canvas(owner)
        if not isinstance(canvas, tk.Canvas):
            messagebox.showerror("Печать", "Не найден Canvas листа для печати", parent=owner)
            return
        win = tk.Toplevel(owner)
        win.title("Предпросмотр печати A4")
        win.geometry("760x920")
        top = ttk.Frame(win, padding=6)
        top.pack(fill=tk.X)
        printers = _v17_enum_printers()  # type: ignore[name-defined]
        default_prn = _v17_default_printer()  # type: ignore[name-defined]
        ttk.Label(top, text="Принтер:").pack(side=tk.LEFT, padx=(0, 4))
        prn_var = tk.StringVar(value=default_prn or (printers[0] if printers else ""))
        combo = ttk.Combobox(top, textvariable=prn_var, values=printers, width=42, state=("readonly" if printers else "normal"))
        combo.pack(side=tk.LEFT, padx=4)
        body = tk.Canvas(win, bg="#555", highlightthickness=0)
        vsb = ttk.Scrollbar(win, orient=tk.VERTICAL, command=body.yview)
        body.configure(yscrollcommand=vsb.set)
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        scale = 0.55
        try:
            cw = int(float(canvas.cget("width"))); ch = int(float(canvas.cget("height")))
        except Exception:
            cw, ch = 1040, 1380
        page = tk.Canvas(body, bg="white", width=int(cw*scale), height=int(ch*scale), bd=1, relief=tk.SOLID, highlightthickness=0)
        body.create_window(14, 14, anchor="nw", window=page)
        body.configure(scrollregion=(0, 0, int(cw*scale)+28, int(ch*scale)+28))
        _v17_clone_canvas_items(canvas, page, scale)  # type: ignore[name-defined]
        safe_title = re.sub(r"[^A-Za-z0-9А-Яа-я_.-]+", "_", str(title or "peleng_sheet"))[:80]
        def do_print() -> None:
            import tempfile
            path = os.path.join(tempfile.gettempdir(), f"{safe_title}.ps")
            _v17_save_postscript(canvas, path)  # type: ignore[name-defined]
            try:
                _v17_print_file_to_printer(path, prn_var.get().strip())  # type: ignore[name-defined]
                messagebox.showinfo("Печать", "Задание отправлено в печать", parent=win)
            except Exception as exc:
                messagebox.showwarning("Печать", f"Не удалось открыть системную печать:\n{exc}\n\nФайл сохранён:\n{path}", parent=win)
        ttk.Button(top, text="Печать", command=do_print).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Закрыть", command=win.destroy).pack(side=tk.RIGHT, padx=4)
    except Exception as exc:
        messagebox.showerror("Печать", str(exc), parent=owner)

# Override v17 global used by already-configured lambdas and reconfigure buttons.
_v17_print_preview = _v18_print_preview  # type: ignore[assignment]
try:
    _v17_wrap_buttons(NativeReportSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(NativeAscanProtocolSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(SettingDetail)  # type: ignore[name-defined]
except Exception:
    pass



# ---------------------------------------------------------------------------
# v19 final compact A4 / graph orientation / clean decoded SQLite pass.
# ---------------------------------------------------------------------------
# Scope of this pass:
#   * keep transport and basket logic unchanged;
#   * fix A4 preview/print scaling so report/protocol/setting pages fit A4;
#   * draw A-scan in native orientation (sample - 0x8C, echo upward);
#   * make protocol diagnostics tolerate live fw byte 0x004B;
#   * create a separate clean decoded SQLite database with exactly 3 user tables:
#     reports, protocols, settings.  The internal working DB still needs raw_records
#     for graph/setting autoload; the clean DB is the user-facing decoded database.

APP_BUILD_VERSION = "v19 compact A4 + native graph + clean decoded SQLite"

# Treat 0x004B in live RESULTS2 as a valid record marker/header byte, not a bad
# firmware.  Firmware shown to the operator still comes from the 55 header16.
try:
    SUPPORTED_FW_CODES.add(0x004B)  # type: ignore[name-defined]
except Exception:
    pass


def _v19_typevar_text(v: Any) -> str:
    try:
        tv = int(_short_typevar(v))  # type: ignore[name-defined]
    except Exception:
        return str(v or "").strip()
    try:
        info = typevar_info_643(tv)  # type: ignore[name-defined]
        obj = str(info.get("object") or "").strip()
        if obj:
            return obj
        detail = str(info.get("detail") or "").strip()
        return detail or str(tv)
    except Exception:
        if tv // 100 == 8:
            return "колесо"
        if tv // 100 == 7:
            return "ось РУ1Ш"
        return str(tv)

# ---------------------------------------------------------------------------
# Clean decoded SQLite mirror: exactly reports/protocols/settings tables, no raw.
# ---------------------------------------------------------------------------

def _v19_clean_db_path(db: Any) -> str:
    try:
        p = Path(str(db.path))
        return str(p.with_name(p.stem + "_decoded.sqlite3"))
    except Exception:
        return "peleng_decoded.sqlite3"


def _v19_clean_connect(db: Any):
    path = _v19_clean_db_path(db)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            report_no TEXT,
            line_no INTEGER,
            device_no TEXT,
            software_version TEXT,
            enterprise TEXT,
            subdivision TEXT,
            operator_code TEXT,
            operator_name TEXT,
            ntd TEXT,
            setting_no TEXT,
            control_date TEXT,
            control_time TEXT,
            typevar TEXT,
            object_type TEXT,
            object_number TEXT,
            smelting TEXT,
            factory TEXT,
            production_year TEXT,
            side TEXT,
            neck TEXT,
            rim TEXT,
            wheel_turning TEXT,
            crest TEXT,
            defects_count TEXT,
            protocol TEXT,
            UNIQUE(report_no,line_no,control_date,control_time,object_number)
        );
        CREATE TABLE IF NOT EXISTS protocols (
            protocol_no TEXT,
            device_no TEXT,
            software_version TEXT,
            control_date TEXT,
            control_time TEXT,
            enterprise TEXT,
            subdivision TEXT,
            operator_code TEXT,
            operator_name TEXT,
            typevar TEXT,
            object_type TEXT,
            object_number TEXT,
            smelting TEXT,
            factory TEXT,
            production_year TEXT,
            side TEXT,
            neck TEXT,
            detail TEXT,
            ntd TEXT,
            setting_no TEXT,
            conclusion TEXT,
            defect_m TEXT,
            defect_y TEXT,
            defect_x TEXT,
            defect_r TEXT,
            defect_detectability TEXT,
            UNIQUE(protocol_no,control_date,control_time,object_number)
        );
        CREATE TABLE IF NOT EXISTS settings (
            setting_no TEXT PRIMARY KEY,
            device_no TEXT,
            software_version TEXT,
            setting_date TEXT,
            setting_time TEXT,
            operator_code TEXT,
            typevar TEXT,
            freq_mhz TEXT,
            sound_speed TEXT,
            thickness_mm TEXT,
            probe_no TEXT,
            probe_enabled TEXT,
            angle_deg TEXT,
            probe_time_us TEXT,
            gain_db TEXT,
            required_sens_db TEXT,
            actual_sens_db TEXT,
            extra_gain_db TEXT,
            sweep_type TEXT,
            sweep_duration TEXT,
            vs1_start TEXT,
            vs1_end TEXT,
            vs1_method TEXT,
            vs1_threshold_pct TEXT,
            vs2_start TEXT,
            vs2_end TEXT,
            vs2_method TEXT,
            vs2_threshold_pct TEXT,
            vrch_type TEXT,
            vrch_start TEXT,
            vrch_end TEXT,
            vrch_amplitude_db TEXT
        );
    """)
    return conn


def _v19_sync_clean_report(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("reports", int(addr))
        if not row:
            return
        vals = _native_report_detail_values(db, row)  # type: ignore[name-defined]
        base = native_report_container_base(int(addr))  # type: ignore[name-defined]
        line_no = int(addr) % 100 or 1
        report_no = str((base % 10000) // 100 if base else vals.get("setting_no") or "")
        operator_code = str(row["KODOPERA"] or "") if "KODOPERA" in row.keys() else ""
        operator_name = _operator_name_for_code(operator_code, str(row["NAMEOPERA"] or "") if "NAMEOPERA" in row.keys() else "")  # type: ignore[name-defined]
        try:
            tv = row["TYPEVAR"] if "TYPEVAR" in row.keys() else vals.get("obj_type")
        except Exception:
            tv = vals.get("obj_type")
        conn = _v19_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO reports(
                    report_no,line_no,device_no,software_version,enterprise,subdivision,
                    operator_code,operator_name,ntd,setting_no,control_date,control_time,
                    typevar,object_type,object_number,smelting,factory,production_year,
                    side,neck,rim,wheel_turning,crest,defects_count,protocol
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                report_no, line_no,
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                _report_enterprise(), _report_subdivision(),  # type: ignore[name-defined]
                operator_code, operator_name,
                str(vals.get("ntd") or "СТО РЖД 1.11.002-2008 (ТИ 07.73-2009)"),
                str(vals.get("setting_no") or ""), str(vals.get("date") or ""), str(vals.get("time") or ""),
                _v19_typevar_text(tv), str(vals.get("obj_type") or _v19_typevar_text(tv)),
                str(vals.get("numobj") or ""), str(vals.get("smelting") or ""), str(vals.get("factory") or ""),
                str(vals.get("year") or ""), str(vals.get("side") or ""), str(vals.get("neck") or ""),
                str(vals.get("rim") or ""), str(vals.get("wheel_turn") or ""), str(vals.get("crest") or ""),
                str(vals.get("defects") or ""), str(row["PROTOCOL"] or "") if "PROTOCOL" in row.keys() else "",
            ))
        conn.close()
    except Exception:
        pass


def _v19_protocol_values(db: Any, row: Any, raw: bytes) -> dict[str, str]:
    vals: dict[str, str] = {}
    try:
        tv = row["TYPEVAR"] if "TYPEVAR" in row.keys() else ""
    except Exception:
        tv = ""
    info = {}
    try:
        info = typevar_info_643(int(_short_typevar(tv)))  # type: ignore[name-defined]
    except Exception:
        pass
    try:
        ptmp = NativeAscanProtocolSheet.__new__(NativeAscanProtocolSheet)  # type: ignore[name-defined]
        ptmp.db = db; ptmp.row = row; ptmp.addr = int(row["address"]); ptmp.protocol_raw = bytes(raw or b"")
        ptmp.setting_no = int(str(row["SETTING_NO"] or "0")) if "SETTING_NO" in row.keys() else 0
        ptmp.setting_addr = int(str(row["SETTING_ADDR"] or "0")) if "SETTING_ADDR" in row.keys() else (1000+ptmp.setting_no if ptmp.setting_no else 0)
        rr = db.get_raw_by_addr(ptmp.setting_addr) if ptmp.setting_addr else None
        ptmp.setting_raw = bytes(rr["raw"]) if rr else b""
        ptmp.setting_params = decode_nastr2_params_643(ptmp.setting_raw, ptmp.setting_addr) if ptmp.setting_raw else {}  # type: ignore[name-defined]
        ptmp.defect = decode_defect_643(bytes(raw or b""), int(ptmp.setting_params.get("sound_speed") or 5900), float(ptmp.setting_params.get("angle_deg") or 0))  # type: ignore[name-defined]
        vals["side"] = NativeAscanProtocolSheet._side_value(ptmp)  # type: ignore[name-defined]
        vals["neck"] = NativeAscanProtocolSheet._neck_value(ptmp)  # type: ignore[name-defined]
        vals["factory"] = NativeAscanProtocolSheet._factory_value(ptmp)  # type: ignore[name-defined]
        vals["year"] = NativeAscanProtocolSheet._year_value(ptmp)  # type: ignore[name-defined]
        vals["object_number"] = NativeAscanProtocolSheet._object_number_value(ptmp)  # type: ignore[name-defined]
        vals["smelting"] = NativeAscanProtocolSheet._smelting_value(ptmp)  # type: ignore[name-defined]
        vals["defect_m"] = str((ptmp.defect or {}).get("reflector_no", "0"))
        vals["defect_y"] = str((ptmp.defect or {}).get("defect_y", "0.0"))
        vals["defect_x"] = str((ptmp.defect or {}).get("defect_x", "0.0"))
        vals["defect_r"] = str((ptmp.defect or {}).get("defect_r", "0.0"))
        vals["defect_detectability"] = str((ptmp.defect or {}).get("detectability_db", "0"))
    except Exception:
        vals.update({"side":"","neck":"","factory":"","year":"","object_number":"","smelting":""})
    vals["object_type"] = str((info or {}).get("object") or _v19_typevar_text(tv))
    vals["detail"] = str((info or {}).get("detail") or "")
    vals["ntd"] = str((info or {}).get("ntd") or "")
    return vals


def _v19_sync_clean_protocol(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("protocols", int(addr))
        rr = db.get_raw_by_addr(int(addr))
        raw = bytes(rr["raw"]) if rr else b""
        if not row:
            return
        vals = _v19_protocol_values(db, row, raw)
        operator_code = str(row["KODOPERA"] or "") if "KODOPERA" in row.keys() else ""
        conn = _v19_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO protocols(
                    protocol_no,device_no,software_version,control_date,control_time,enterprise,subdivision,
                    operator_code,operator_name,typevar,object_type,object_number,smelting,factory,production_year,
                    side,neck,detail,ntd,setting_no,conclusion,defect_m,defect_y,defect_x,defect_r,defect_detectability
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(row["NUMKOD"] or "") if "NUMKOD" in row.keys() else str(int(addr)%1000),
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                str(row["DATEFORM"] or "") if "DATEFORM" in row.keys() else "",
                str(row["TIMEFORM"] or "") if "TIMEFORM" in row.keys() else "",
                _report_enterprise(), _report_subdivision(),  # type: ignore[name-defined]
                operator_code, _operator_name_for_code(operator_code, str(row["NAMEOPERA"] or "") if "NAMEOPERA" in row.keys() else ""),  # type: ignore[name-defined]
                _v19_typevar_text(row["TYPEVAR"] if "TYPEVAR" in row.keys() else ""), vals.get("object_type",""), vals.get("object_number",""), vals.get("smelting",""), vals.get("factory",""), vals.get("year",""), vals.get("side",""), vals.get("neck",""), vals.get("detail",""), vals.get("ntd",""),
                str(row["SETTING_NO"] or "") if "SETTING_NO" in row.keys() else "",
                "Признак дефекта отсутствует", vals.get("defect_m",""), vals.get("defect_y",""), vals.get("defect_x",""), vals.get("defect_r",""), vals.get("defect_detectability",""),
            ))
        conn.close()
    except Exception:
        pass


def _v19_sync_clean_setting(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("settings", int(addr))
        rr = db.get_raw_by_addr(int(addr))
        raw = bytes(rr["raw"]) if rr else b""
        if not row:
            return
        p = decode_nastr2_params_643(raw, int(addr)) if raw else {}  # type: ignore[name-defined]
        conn = _v19_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO settings(
                    setting_no,device_no,software_version,setting_date,setting_time,operator_code,typevar,
                    freq_mhz,sound_speed,thickness_mm,probe_no,probe_enabled,angle_deg,probe_time_us,
                    gain_db,required_sens_db,actual_sens_db,extra_gain_db,sweep_type,sweep_duration,
                    vs1_start,vs1_end,vs1_method,vs1_threshold_pct,vs2_start,vs2_end,vs2_method,vs2_threshold_pct,
                    vrch_type,vrch_start,vrch_end,vrch_amplitude_db
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(p.get("setting_no") or (int(addr)-1000 if 1000 <= int(addr) <= 1999 else int(addr))),
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                str(p.get("date") or row["DATEFORM"] if "DATEFORM" in row.keys() else ""),
                str(p.get("time") or row["TIMEFORM"] if "TIMEFORM" in row.keys() else ""),
                str(p.get("operator_code") or row["KODOPERA"] if "KODOPERA" in row.keys() else ""),
                _v19_typevar_text(p.get("typevar_code") or row["TYPEVAR"] if "TYPEVAR" in row.keys() else ""),
                str(p.get("freq_mhz") or ""), str(p.get("sound_speed") or ""), str(p.get("thickness_mm") or ""),
                str(p.get("probe_no") or ""), str(p.get("probe_enabled") or ""), str(p.get("angle_deg") or ""), str(p.get("probe_time_us") or ""),
                str(p.get("gain_db") or ""), str(p.get("required_sens_db") or ""), str(p.get("actual_sens_db") or ""), str(p.get("extra_gain_db") or ""),
                str(p.get("sweep_type") or ""), str(p.get("sweep_duration") or ""),
                str(p.get("vs1_start") or ""), str(p.get("vs1_end") or ""), str(p.get("vs1_method") or ""), str(p.get("vs1_threshold_pct") or ""),
                str(p.get("vs2_start") or ""), str(p.get("vs2_end") or ""), str(p.get("vs2_method") or ""), str(p.get("vs2_threshold_pct") or ""),
                str(p.get("vrch_type") or p.get("vrch_enabled") or ""), str(p.get("vrch_start") or ""), str(p.get("vrch_end") or ""), str(p.get("vrch_amplitude_db") or p.get("vrch_amplitude") or ""),
            ))
        conn.close()
    except Exception:
        pass

# Wrap PelengDB save_* so the operator gets a clean decoded SQLite file with
# only three tables.  The internal file still exists for runtime graph/raw lookup.
try:
    _v19_old_save_report = PelengDB.save_report  # type: ignore[name-defined]
    def _v19_save_report(self, raw_id: int, addr: int, fields: dict[str, str]) -> None:
        _v19_old_save_report(self, raw_id, addr, fields)
        _v19_sync_clean_report(self, int(addr))
    PelengDB.save_report = _v19_save_report  # type: ignore[name-defined]

    _v19_old_save_protocol = PelengDB.save_protocol  # type: ignore[name-defined]
    def _v19_save_protocol(self, raw_id: int, addr: int, fields: dict[str, str]) -> None:
        _v19_old_save_protocol(self, raw_id, addr, fields)
        _v19_sync_clean_protocol(self, int(addr))
    PelengDB.save_protocol = _v19_save_protocol  # type: ignore[name-defined]

    _v19_old_save_setting = PelengDB.save_setting  # type: ignore[name-defined]
    def _v19_save_setting(self, raw_id: int, addr: int, fields: dict[str, str], params: dict[str, Any]) -> None:
        _v19_old_save_setting(self, raw_id, addr, fields, params)
        _v19_sync_clean_setting(self, int(addr))
    PelengDB.save_setting = _v19_save_setting  # type: ignore[name-defined]
except Exception:
    pass

# ---------------------------------------------------------------------------
# A4 print preview and fit-to-page PostScript.
# ---------------------------------------------------------------------------
V19_A4_W = 794
V19_A4_H = 1123


def _v19_scaled_font(font_desc: Any, scale: float) -> Any:
    try:
        s = str(font_desc or "Arial 9")
        parts = s.split()
        out = []
        done = False
        for part in parts:
            try:
                n = int(part)
                if not done and -200 < n < 200:
                    sign = -1 if n < 0 else 1
                    nn = max(4, int(abs(n) * scale))
                    out.append(str(sign * nn))
                    done = True
                    continue
            except Exception:
                pass
            out.append(part)
        if not done:
            out.append(str(max(4, int(9 * scale))))
        return " ".join(out)
    except Exception:
        return ("Arial", max(4, int(9 * scale)))


def _v19_clone_canvas_items(src: tk.Canvas, dst: tk.Canvas, scale: float = 1.0, ox: float = 0.0, oy: float = 0.0) -> None:
    def sc(vals: list[float]) -> list[float]:
        return [ox + vals[i] * scale if i % 2 == 0 else oy + vals[i] * scale for i in range(len(vals))]
    for item in src.find_all():
        try:
            typ = src.type(item)
            coords = [float(v) for v in src.coords(item)]
            if typ == "line":
                dst.create_line(*sc(coords), fill=src.itemcget(item,"fill") or "#111", dash=src.itemcget(item,"dash"), width=max(1, int(float(src.itemcget(item,"width") or 1)*scale)))
            elif typ == "rectangle":
                dst.create_rectangle(*sc(coords), outline=src.itemcget(item,"outline") or "#111", fill=src.itemcget(item,"fill") or "")
            elif typ == "text":
                opts: dict[str, Any] = {
                    "text": src.itemcget(item,"text"),
                    "fill": src.itemcget(item,"fill") or "#111",
                    "anchor": src.itemcget(item,"anchor") or "nw",
                    "font": _v19_scaled_font(src.itemcget(item,"font") or "Arial 9", scale),
                }
                try:
                    width_s = src.itemcget(item,"width")
                    if width_s and float(width_s) > 0:
                        opts["width"] = max(1, int(float(width_s)*scale))
                except Exception:
                    pass
                xy = sc(coords[:2]) if coords else [ox,oy]
                dst.create_text(xy[0], xy[1], **opts)
            elif typ == "window":
                win_name = src.itemcget(item,"window")
                if win_name and coords:
                    try:
                        child = src.nametowidget(win_name)
                        if isinstance(child, tk.Canvas):
                            _v19_clone_canvas_items(child, dst, scale, ox + coords[0]*scale, oy + coords[1]*scale)
                    except Exception:
                        pass
        except Exception:
            continue


def _v19_a4_canvas_from(src: tk.Canvas, owner: tk.Misc, margin: int = 28) -> tk.Canvas:
    try:
        src.update_idletasks()
        cw = int(float(src.cget("width"))); ch = int(float(src.cget("height")))
    except Exception:
        cw, ch = 1040, 1380
    # If source is report-like landscape table, still force portrait A4 but make
    # text and columns scale correctly.  The content is fitted into the printable
    # area, so it will not overflow A4.
    scale = min((V19_A4_W - margin*2) / max(1, cw), (V19_A4_H - margin*2) / max(1, ch))
    scale = min(scale, 1.0)
    c = tk.Canvas(owner, bg="white", width=V19_A4_W, height=V19_A4_H, highlightthickness=0)
    _v19_clone_canvas_items(src, c, scale, margin, margin)
    return c


def _v19_save_postscript(canvas: tk.Canvas, path: str) -> None:
    canvas.update_idletasks()
    canvas.postscript(file=path, colormode="gray", pagewidth="210m", pageheight="297m", rotate=False)

# Replace old save function used by preview.
_v17_save_postscript = _v19_save_postscript  # type: ignore[assignment]


def _v19_make_report_print_canvas(owner: Any) -> Optional[tk.Canvas]:
    """A4 portrait report canvas with small fonts and no overlapped columns."""
    try:
        rows = owner._rows_for_group()
    except Exception:
        return None
    c = tk.Canvas(owner, bg="white", width=V19_A4_W, height=V19_A4_H, highlightthickness=0)
    try:
        first = rows[0] if rows else None
        vals0 = _native_report_detail_values(owner.db, first) if first else {}  # type: ignore[name-defined]
        device = str(first["NUMPRIB"] if first and "NUMPRIB" in first.keys() else "")
        version = str(first["NUMVERS"] if first and "NUMVERS" in first.keys() else "")
        report_no = getattr(owner, 'group_base', 0) % 10000 // 100 if getattr(owner, 'group_base', 0) else ''
        c.create_text(34, 34, text=f"ОТЧЕТ № {report_no}", anchor="nw", font=("Arial", 10, "bold"))
        c.create_text(34, 58, text=f"о контроле дефектоскопом УД2-102 № {device}, Версия {version}", anchor="nw", font=("Arial", 8))
        operator_code = str(first["KODOPERA"] if first else "")
        operator_name = _operator_name_for_code(operator_code)  # type: ignore[name-defined]
        lines = [("Предприятие", _report_enterprise()), ("Подразделение", _report_subdivision()), ("Оператор: шифр", operator_code), ("Фамилия", operator_name), ("НТД на контроль", "СТО РЖД 1.11.002-2008 (ТИ 07.73-2009)"), ("Номер настройки", str(vals0.get("setting_no", "")))]  # type: ignore[name-defined]
        y = 95
        for k, v in lines:
            c.create_text(34, y, text=k, anchor="nw", font=("Arial", 7))
            c.create_text(150, y, text=str(v), anchor="nw", font=("Arial", 8, "bold" if k in ("Предприятие","Подразделение","Фамилия","НТД на контроль") else "normal"), width=600)
            y += 18
        cols = ["№", "Дата", "Объект", "Номер объекта", "Плавка", "З-д", "Год", "Стор", "шейка", "обод", "обт.", "греб.", "деф"]
        widths = [24, 52, 92, 84, 58, 35, 35, 36, 68, 62, 52, 52, 34]
        x0, y0 = 28, 215
        row_h = 17
        x = x0
        for title, ww in zip(cols, widths):
            c.create_rectangle(x, y0, x+ww, y0+row_h, outline="#111", fill="#eee")
            c.create_text(x+2, y0+3, text=title, anchor="nw", font=("Arial", 5, "bold"), width=ww-3)
            x += ww
        max_rows = min(len(rows), 48)
        for i, row in enumerate(rows[:max_rows], 1):
            vals = _native_report_detail_values(owner.db, row)  # type: ignore[name-defined]
            line = [str(i), _native_report_display_date(vals["date"]), vals["obj_type"], vals["numobj"], vals["smelting"], vals["factory"], vals["year"], vals["side"], vals["neck"], vals["rim"], vals["wheel_turn"], vals["crest"], vals["defects"]]  # type: ignore[name-defined]
            x = x0; yy = y0 + row_h*i
            for val, ww in zip(line, widths):
                c.create_rectangle(x, yy, x+ww, yy+row_h, outline="#111")
                c.create_text(x+2, yy+3, text=str(val), anchor="nw", font=("Arial", 5), width=ww-3)
                x += ww
        c.create_text(V19_A4_W//2, V19_A4_H-54, text="Подпись:", anchor="center", font=("Arial", 8))
        owner.page_canvas = c
        return c
    except Exception:
        try: c.destroy()
        except Exception: pass
        return None


def _v19_print_preview(owner: tk.Misc, canvas: Optional[tk.Canvas] = None, title: str = "peleng_sheet") -> None:
    try:
        if canvas is None:
            canvas = getattr(owner, "page_canvas", None)
        if not isinstance(canvas, tk.Canvas):
            canvas = _v19_make_report_print_canvas(owner)
        if not isinstance(canvas, tk.Canvas):
            messagebox.showerror("Печать", "Не найден Canvas листа для печати", parent=owner)
            return
        # Create a fitted A4 canvas used for both preview and actual print.
        a4_canvas = canvas if (int(float(canvas.cget("width"))) == V19_A4_W and int(float(canvas.cget("height"))) == V19_A4_H) else _v19_a4_canvas_from(canvas, owner)
        win = tk.Toplevel(owner)
        win.title("Предпросмотр печати A4")
        win.geometry("720x900")
        top = ttk.Frame(win, padding=6); top.pack(fill=tk.X)
        printers = _v17_enum_printers()  # type: ignore[name-defined]
        default_prn = _v17_default_printer()  # type: ignore[name-defined]
        ttk.Label(top, text="Принтер:").pack(side=tk.LEFT, padx=(0, 4))
        prn_var = tk.StringVar(value=default_prn or (printers[0] if printers else ""))
        ttk.Combobox(top, textvariable=prn_var, values=printers, width=42, state=("readonly" if printers else "normal")).pack(side=tk.LEFT, padx=4)
        body = tk.Canvas(win, bg="#555", highlightthickness=0)
        vsb = ttk.Scrollbar(win, orient=tk.VERTICAL, command=body.yview)
        body.configure(yscrollcommand=vsb.set)
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); vsb.pack(side=tk.RIGHT, fill=tk.Y)
        scale = 0.70
        page = tk.Canvas(body, bg="white", width=int(V19_A4_W*scale), height=int(V19_A4_H*scale), bd=1, relief=tk.SOLID, highlightthickness=0)
        body.create_window(14, 14, anchor="nw", window=page)
        body.configure(scrollregion=(0,0,int(V19_A4_W*scale)+28,int(V19_A4_H*scale)+28))
        _v19_clone_canvas_items(a4_canvas, page, scale)
        safe_title = re.sub(r"[^A-Za-z0-9А-Яа-я_.-]+", "_", str(title or "peleng_sheet"))[:80]
        def do_print() -> None:
            import tempfile
            path = os.path.join(tempfile.gettempdir(), f"{safe_title}.ps")
            _v19_save_postscript(a4_canvas, path)
            try:
                _v17_print_file_to_printer(path, prn_var.get().strip())  # type: ignore[name-defined]
                messagebox.showinfo("Печать", "Задание отправлено в печать", parent=win)
            except Exception as exc:
                messagebox.showwarning("Печать", f"Не удалось открыть системную печать:\n{exc}\n\nФайл сохранён:\n{path}", parent=win)
        ttk.Button(top, text="Печать", command=do_print).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Закрыть", command=win.destroy).pack(side=tk.RIGHT, padx=4)
    except Exception as exc:
        messagebox.showerror("Печать", str(exc), parent=owner)

_v17_print_preview = _v19_print_preview  # type: ignore[assignment]
_v18_print_preview = _v19_print_preview  # type: ignore[assignment]
try:
    _v17_wrap_buttons(NativeReportSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(NativeAscanProtocolSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(SettingDetail)  # type: ignore[name-defined]
except Exception:
    pass

# Smooth report opening: build while hidden and show after geometry is ready.
try:
    def _v19_report_init(self, master: tk.Misc, db: PelengDB, selected_addr: int):  # type: ignore[name-defined]
        tk.Toplevel.__init__(self, master)
        self.withdraw()
        self.db = db
        self.selected_addr = int(selected_addr)
        self.group_base = native_report_container_base(self.selected_addr)  # type: ignore[name-defined]
        self.title("Отчет о контроле")
        self.geometry("1180x780")
        self.minsize(980, 620)
        self.configure(bg="#efefef")
        self._build()
        self.update_idletasks()
        self.after(80, lambda: (self.deiconify(), self.lift(), self.focus_force()))
    NativeReportSheet.__init__ = _v19_report_init  # type: ignore[name-defined]
except Exception:
    pass

# Native graph orientation: original printed trace is near the baseline with
# upward echoes.  Use sample-0x8C, not 0x8C-sample; keep zones visible.
def _v19_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    c = self.graph_canvas
    c.delete("all")
    w, h = 360, 230
    x0, y0 = 12, 10
    x1, y1 = w - 14, h - 30
    pw, ph = x1 - x0, y1 - y0
    baseline_y = y1 - 18
    c.create_rectangle(x0, y0, x1, y1, outline="#222")
    for i in range(1, 10):
        x = x0 + pw*i/10.0
        c.create_line(x, y0, x, y1, fill="#cfcfcf", dash=(1,5))
    for i in range(1, 7):
        y = y0 + ph*i/7.0
        c.create_line(x0, y, x1, y, fill="#cfcfcf", dash=(1,5))
    zone = _v14_zone_values(self)  # type: ignore[name-defined]
    duration = int(_v16_safe_float(zone.get("duration_t10"), 7920)) or 7920  # type: ignore[name-defined]
    def x_by_t10(v: Any) -> float:
        rx = max(0.0, _v16_safe_float(v,0.0))  # type: ignore[name-defined]
        return max(x0, min(x1, x0 + rx/max(1,duration)*pw))
    def gate(a: Any, b: Any, label: str, dash: tuple[int,int], ylab: int) -> None:
        aa = _v16_safe_float(a,0.0); bb = _v16_safe_float(b,0.0)  # type: ignore[name-defined]
        if aa <= 0 and bb <= 0: return
        if bb < aa: aa,bb = bb,aa
        xa, xb = x_by_t10(aa), x_by_t10(bb)
        if xb-xa < 2: xb = xa+2
        c.create_line(xa, y0+2, xa, y1-2, fill="#222", dash=dash, width=1)
        c.create_line(xb, y0+2, xb, y1-2, fill="#222", dash=dash, width=1)
        c.create_text((xa+xb)/2, y0+ylab, text=label, fill="#111", font=("Arial",8,"bold"))
    gate(zone.get("vrch_start_raw"), zone.get("vrch_end_raw"), "ВРЧ", (1,4), 10)
    gate(zone.get("vs1_start_raw"), zone.get("vs1_end_raw"), "ВС1", (3,3), 24)
    gate(zone.get("vs2_start_raw"), zone.get("vs2_end_raw"), "ВС2", (5,2), 10)
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")
    samples = [int(s)&0xFF for s in ((self.graph or {}).get("samples") or [])][:GRAPH_DRAW_COUNT]
    if len(samples) < 2:
        c.create_text((x0+x1)/2, (y0+y1)/2, text=(self.graph or {}).get("error", "Нет графика"), fill="#555", width=pw-10)
        return
    amps = [max(0, int(s)-GRAPH_BASELINE) for s in samples]
    # If this candidate is completely flat in native orientation, keep the line
    # at baseline instead of inverting.  This avoids the false high plateau.
    p98 = max(1.0, _v17_percentile([float(a) for a in amps if a > 0], 0.98, max(amps or [1])))  # type: ignore[name-defined]
    gain = min(12.0, max(0.6, (ph*0.78)/p98))
    pts: list[float] = []
    for i, ap in enumerate(amps):
        x = x0 + (i/max(1,len(amps)-1))*pw
        y = baseline_y - float(ap)*gain
        y = max(y0+2, min(y1-2, y))
        pts.extend((x,y))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)
    # Marker from exact R/Y or strongest tail echo.
    mx = my = None
    try:
        r_mm = _v16_safe_float((self.defect or {}).get("defect_r"), 0.0)  # type: ignore[name-defined]
        if r_mm > 0:
            speed = _v16_safe_float((getattr(self,"setting_params",{}) or {}).get("sound_speed"),5900.0)  # type: ignore[name-defined]
            mx = x_by_t10(round(r_mm*20000.0/max(1.0,speed)))
            y_mm = _v16_safe_float((self.defect or {}).get("defect_y"),0.0)  # type: ignore[name-defined]
            ratio = max(0.05,min(0.95,y_mm/r_mm)) if r_mm > 1 and y_mm >= 0 else 0.50
            my = y1 - 10 - ratio*(ph*0.70)
    except Exception:
        pass
    if mx is None or my is None:
        tail_start = max(0, int(len(amps)*0.70))
        idx, a = max(enumerate(amps), key=lambda ia: ia[1] + (25 if ia[0] >= tail_start else 0))
        mx = x0 + (idx/max(1,len(amps)-1))*pw
        my = baseline_y - float(a)*gain
    mx = max(x0+8,min(x1-8,float(mx))); my = max(y0+8,min(y1-8,float(my)))
    c.create_line(mx-8,my,mx+8,my,fill="#222"); c.create_line(mx,my-8,mx,my+8,fill="#222")

try:
    NativeAscanProtocolSheet._draw_native_graph = _v19_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass




# ---------------------------------------------------------------------------
# v20: compact print preview, robust A-scan drawing, clean user SQLite schema.
# ---------------------------------------------------------------------------
APP_BUILD_VERSION = "v20 compact preview + robust graph + clean decoded SQLite"

# The operator-facing decoded SQLite file.  Runtime still needs an internal
# working DB while the app is open (for auto-refetch, graph sources and linked
# settings), but this exported user DB contains only three decoded tables.
def _v20_user_db_path(db: Any) -> str:
    try:
        p = Path(str(db.path))
        return str(p.with_name(p.stem + "_decoded_user.sqlite3"))
    except Exception:
        return "peleng_decoded_user.sqlite3"

_V20_SCHEMA_READY: set[str] = set()

def _v20_clean_connect(db: Any):
    path = _v20_user_db_path(db)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    if path not in _V20_SCHEMA_READY:
        # These are the only user-facing decoded tables.  No raw bytes, no raw_id,
        # no NUMKOD/NUMBER/NUMZAP/created_at, no duplicate typevar/object_type/ntd.
        conn.executescript("""
            DROP TABLE IF EXISTS reports;
            DROP TABLE IF EXISTS protocols;
            DROP TABLE IF EXISTS settings;
            CREATE TABLE reports (
                control_date TEXT,
                control_time TEXT,
                device_no TEXT,
                software_version TEXT,
                enterprise TEXT,
                subdivision TEXT,
                operator_code TEXT,
                operator_name TEXT,
                setting_no TEXT,
                object_type TEXT,
                object_number TEXT,
                smelting TEXT,
                factory TEXT,
                production_year TEXT,
                side TEXT,
                neck TEXT,
                rim TEXT,
                wheel_turning TEXT,
                crest TEXT,
                defects_count TEXT,
                protocol TEXT
            );
            CREATE TABLE protocols (
                protocol_no TEXT,
                control_date TEXT,
                control_time TEXT,
                device_no TEXT,
                software_version TEXT,
                enterprise TEXT,
                subdivision TEXT,
                operator_code TEXT,
                operator_name TEXT,
                setting_no TEXT,
                object_type TEXT,
                object_number TEXT,
                smelting TEXT,
                factory TEXT,
                production_year TEXT,
                side TEXT,
                neck TEXT,
                detail TEXT,
                conclusion TEXT,
                defect_m TEXT,
                defect_y TEXT,
                defect_x TEXT,
                defect_r TEXT,
                defect_detectability TEXT
            );
            CREATE TABLE settings (
                setting_no TEXT,
                setting_date TEXT,
                setting_time TEXT,
                device_no TEXT,
                software_version TEXT,
                operator_code TEXT,
                object_type TEXT,
                freq_mhz TEXT,
                sound_speed TEXT,
                thickness_mm TEXT,
                amplitude_probe TEXT,
                cutoff_pct TEXT,
                blocking TEXT,
                probe_no TEXT,
                probe_enabled TEXT,
                angle_deg TEXT,
                probe_time_us TEXT,
                gain_db TEXT,
                required_sens_db TEXT,
                actual_sens_db TEXT,
                extra_gain_db TEXT,
                sweep_type TEXT,
                sweep_duration TEXT,
                sweep_delay TEXT,
                w_sweep_enabled TEXT,
                envelope_enabled TEXT,
                so_start TEXT,
                so_end TEXT,
                vs1_start TEXT,
                vs1_end TEXT,
                vs1_method TEXT,
                vs1_threshold_pct TEXT,
                vs2_start TEXT,
                vs2_end TEXT,
                vs2_method TEXT,
                vs2_threshold_pct TEXT,
                aru_enabled TEXT,
                aru_start TEXT,
                aru_end TEXT,
                vrch_type TEXT,
                vrch_indication TEXT,
                vrch_start TEXT,
                vrch_end TEXT,
                vrch_amplitude_db TEXT,
                vrch_shape TEXT,
                before_vrch_db TEXT,
                after_vrch_db TEXT,
                extra_gain_enabled TEXT
            );
        """)
        conn.commit()
        _V20_SCHEMA_READY.add(path)
    return conn

# Override the v19 clean DB helpers with a simpler 3-table user schema.
_v19_clean_db_path = _v20_user_db_path  # type: ignore[assignment]
_v19_clean_connect = _v20_clean_connect  # type: ignore[assignment]

def _v20_sync_clean_report(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("reports", int(addr))
        if not row:
            return
        vals = _native_report_detail_values(db, row)  # type: ignore[name-defined]
        operator_code = str(row["KODOPERA"] or "") if "KODOPERA" in row.keys() else ""
        operator_name = _operator_name_for_code(operator_code, str(row["NAMEOPERA"] or "") if "NAMEOPERA" in row.keys() else "")  # type: ignore[name-defined]
        tv = row["TYPEVAR"] if "TYPEVAR" in row.keys() else vals.get("obj_type")
        object_type = str(vals.get("obj_type") or _v19_typevar_text(tv))  # type: ignore[name-defined]
        conn = _v20_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT INTO reports(
                    control_date,control_time,device_no,software_version,enterprise,subdivision,
                    operator_code,operator_name,setting_no,object_type,object_number,smelting,
                    factory,production_year,side,neck,rim,wheel_turning,crest,defects_count,protocol
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(vals.get("date") or ""), str(vals.get("time") or ""),
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                _report_enterprise(), _report_subdivision(), operator_code, operator_name,  # type: ignore[name-defined]
                str(vals.get("setting_no") or ""), object_type, str(vals.get("numobj") or ""),
                str(vals.get("smelting") or ""), str(vals.get("factory") or ""),
                str(vals.get("year") or ""), str(vals.get("side") or ""), str(vals.get("neck") or ""),
                str(vals.get("rim") or ""), str(vals.get("wheel_turn") or ""), str(vals.get("crest") or ""),
                str(vals.get("defects") or ""), str(row["PROTOCOL"] or "") if "PROTOCOL" in row.keys() else "",
            ))
        conn.close()
    except Exception:
        pass


def _v20_sync_clean_protocol(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("protocols", int(addr))
        rr = db.get_raw_by_addr(int(addr))
        raw = bytes(rr["raw"]) if rr else b""
        if not row:
            return
        vals = _v19_protocol_values(db, row, raw)  # type: ignore[name-defined]
        operator_code = str(row["KODOPERA"] or "") if "KODOPERA" in row.keys() else ""
        conn = _v20_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT INTO protocols(
                    protocol_no,control_date,control_time,device_no,software_version,enterprise,subdivision,
                    operator_code,operator_name,setting_no,object_type,object_number,smelting,factory,
                    production_year,side,neck,detail,conclusion,defect_m,defect_y,defect_x,defect_r,defect_detectability
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(row["NUMKOD"] or "") if "NUMKOD" in row.keys() else str(int(addr)%1000),
                str(row["DATEFORM"] or "") if "DATEFORM" in row.keys() else "",
                str(row["TIMEFORM"] or "") if "TIMEFORM" in row.keys() else "",
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                _report_enterprise(), _report_subdivision(), operator_code,  # type: ignore[name-defined]
                _operator_name_for_code(operator_code, str(row["NAMEOPERA"] or "") if "NAMEOPERA" in row.keys() else ""),  # type: ignore[name-defined]
                str(row["SETTING_NO"] or "") if "SETTING_NO" in row.keys() else "",
                vals.get("object_type",""), vals.get("object_number",""), vals.get("smelting",""),
                vals.get("factory",""), vals.get("year",""), vals.get("side",""), vals.get("neck",""),
                vals.get("detail",""), "Признак дефекта отсутствует", vals.get("defect_m",""),
                vals.get("defect_y",""), vals.get("defect_x",""), vals.get("defect_r",""), vals.get("defect_detectability",""),
            ))
        conn.close()
    except Exception:
        pass


def _v20_sync_clean_setting(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("settings", int(addr))
        rr = db.get_raw_by_addr(int(addr))
        raw = bytes(rr["raw"]) if rr else b""
        if not row:
            return
        p = decode_nastr2_params_643(raw, int(addr)) if raw else {}  # type: ignore[name-defined]
        tv = p.get("typevar_code") or (row["TYPEVAR"] if "TYPEVAR" in row.keys() else "")
        conn = _v20_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT INTO settings(
                    setting_no,setting_date,setting_time,device_no,software_version,operator_code,object_type,
                    freq_mhz,sound_speed,thickness_mm,amplitude_probe,cutoff_pct,blocking,probe_no,probe_enabled,
                    angle_deg,probe_time_us,gain_db,required_sens_db,actual_sens_db,extra_gain_db,sweep_type,
                    sweep_duration,sweep_delay,w_sweep_enabled,envelope_enabled,so_start,so_end,vs1_start,vs1_end,
                    vs1_method,vs1_threshold_pct,vs2_start,vs2_end,vs2_method,vs2_threshold_pct,aru_enabled,
                    aru_start,aru_end,vrch_type,vrch_indication,vrch_start,vrch_end,vrch_amplitude_db,vrch_shape,
                    before_vrch_db,after_vrch_db,extra_gain_enabled
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(p.get("setting_no") or (int(addr)-1000 if 1000 <= int(addr) <= 1999 else int(addr))),
                str(p.get("date") or row["DATEFORM"] if "DATEFORM" in row.keys() else ""),
                str(p.get("time") or row["TIMEFORM"] if "TIMEFORM" in row.keys() else ""),
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                str(p.get("operator_code") or row["KODOPERA"] if "KODOPERA" in row.keys() else ""),
                _v19_typevar_text(tv),  # type: ignore[name-defined]
                str(p.get("freq_mhz") or ""), str(p.get("sound_speed") or ""), str(p.get("thickness_mm") or ""),
                str(p.get("amplitude_probe") or ""), str(p.get("cutoff_pct") or ""), str(p.get("blocking") or ""),
                str(p.get("probe_no") or ""), str(p.get("probe_enabled") or ""), str(p.get("angle_deg") or ""),
                str(p.get("probe_time_us") or ""), str(p.get("gain_db") or ""), str(p.get("required_sens_db") or ""),
                str(p.get("actual_sens_db") or ""), str(p.get("extra_gain_db") or ""), str(p.get("sweep_type") or ""),
                str(p.get("sweep_duration") or ""), str(p.get("sweep_delay") or ""), str(p.get("w_sweep_enabled") or ""),
                str(p.get("envelope_enabled") or ""), str(p.get("so_start") or ""), str(p.get("so_end") or ""),
                str(p.get("vs1_start") or ""), str(p.get("vs1_end") or ""), str(p.get("vs1_method") or ""),
                str(p.get("vs1_threshold_pct") or ""), str(p.get("vs2_start") or ""), str(p.get("vs2_end") or ""),
                str(p.get("vs2_method") or ""), str(p.get("vs2_threshold_pct") or ""), str(p.get("aru_enabled") or ""),
                str(p.get("aru_start") or ""), str(p.get("aru_end") or ""), str(p.get("vrch_type") or p.get("vrch_enabled") or ""),
                str(p.get("vrch_indication") or ""), str(p.get("vrch_start") or ""), str(p.get("vrch_end") or ""),
                str(p.get("vrch_amp_db") or p.get("vrch_amplitude_db") or p.get("vrch_amplitude") or ""),
                str(p.get("vrch_shape") or ""), str(p.get("before_vrch_db") or ""), str(p.get("after_vrch_db") or ""),
                str(p.get("extra_gain_enabled") or ""),
            ))
        conn.close()
    except Exception:
        pass

_v19_sync_clean_report = _v20_sync_clean_report  # type: ignore[assignment]
_v19_sync_clean_protocol = _v20_sync_clean_protocol  # type: ignore[assignment]
_v19_sync_clean_setting = _v20_sync_clean_setting  # type: ignore[assignment]

# Robust graph rendering: draw a visible trace even when the graph block is below
# the old 0x8C baseline, but remove the DC plateau before scaling. This follows
# the native envelope view: baseline at the bottom, echoes upward, zones overlaid.
def _v20_percentile(vals: list[float], q: float, default: float = 0.0) -> float:
    vals = sorted(float(v) for v in vals if v is not None)
    if not vals:
        return float(default)
    if len(vals) == 1:
        return vals[0]
    pos = max(0.0, min(1.0, q)) * (len(vals)-1)
    lo = int(pos); hi = min(len(vals)-1, lo+1)
    frac = pos - lo
    return vals[lo]*(1-frac) + vals[hi]*frac


def _v20_graph_curve(samples: list[int]) -> tuple[list[float], str]:
    if not samples:
        return [], "empty"
    smin, smax = min(samples), max(samples)
    candidates: list[tuple[float, list[float], str]] = []
    raw_candidates = [
        ([float(s - GRAPH_BASELINE) for s in samples], "sample_minus_0x8C"),
        ([float(GRAPH_BASELINE - s) for s in samples], "0x8C_minus_sample"),
        ([float(s - smin) for s in samples], "sample_minus_min"),
        ([float(smax - s) for s in samples], "max_minus_sample"),
    ]
    tail0 = max(0, int(len(samples)*0.72))
    for vals, name in raw_candidates:
        floor = _v20_percentile(vals, 0.08, min(vals) if vals else 0.0)
        dyn = [max(0.0, v - floor) for v in vals]
        p98 = _v20_percentile([v for v in dyn if v > 0], 0.98, max(dyn or [0.0]))
        tail = max(dyn[tail0:] or [0.0])
        mid = max(dyn[int(len(dyn)*0.05):int(len(dyn)*0.65)] or [0.0])
        # Prefer a visible tail/right echo but avoid a full-height plateau.
        plateau_penalty = _v20_percentile(dyn, 0.50, 0.0) * 0.35
        score = tail*2.2 + p98*0.9 + mid*0.15 - plateau_penalty
        candidates.append((score, dyn, name))
    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0]
    return best[1], best[2]


def _v20_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    c = self.graph_canvas
    c.delete("all")
    w, h = 360, 230
    x0, y0 = 12, 10
    x1, y1 = w - 14, h - 30
    pw, ph = x1 - x0, y1 - y0
    baseline_y = y1 - 18
    c.create_rectangle(x0, y0, x1, y1, outline="#222")
    for i in range(1, 10):
        x = x0 + pw*i/10.0
        c.create_line(x, y0, x, y1, fill="#cfcfcf", dash=(1,5))
    for i in range(1, 7):
        y = y0 + ph*i/7.0
        c.create_line(x0, y, x1, y, fill="#cfcfcf", dash=(1,5))
    zone = _v14_zone_values(self)  # type: ignore[name-defined]
    duration = int(_v16_safe_float(zone.get("duration_t10"), 7920)) or 7920  # type: ignore[name-defined]
    def x_by_t10(v: Any) -> float:
        rx = max(0.0, _v16_safe_float(v,0.0))  # type: ignore[name-defined]
        return max(x0, min(x1, x0 + rx/max(1,duration)*pw))
    def gate(a: Any, b: Any, label: str, dash: tuple[int,int], ylab: int) -> None:
        aa = _v16_safe_float(a,0.0); bb = _v16_safe_float(b,0.0)  # type: ignore[name-defined]
        if aa <= 0 and bb <= 0:
            return
        if bb < aa:
            aa,bb = bb,aa
        xa, xb = x_by_t10(aa), x_by_t10(bb)
        if xb-xa < 2:
            xb = xa+2
        c.create_line(xa, y0+2, xa, y1-2, fill="#222", dash=dash, width=1)
        c.create_line(xb, y0+2, xb, y1-2, fill="#222", dash=dash, width=1)
        c.create_text((xa+xb)/2, y0+ylab, text=label, fill="#111", font=("Arial",8,"bold"))
    gate(zone.get("vrch_start_raw"), zone.get("vrch_end_raw"), "ВРЧ", (1,4), 10)
    gate(zone.get("vs1_start_raw"), zone.get("vs1_end_raw"), "ВС1", (3,3), 24)
    gate(zone.get("vs2_start_raw"), zone.get("vs2_end_raw"), "ВС2", (5,2), 10)
    c.create_line(x0, baseline_y, x1, baseline_y, fill="#777")
    samples = [int(s)&0xFF for s in ((self.graph or {}).get("samples") or [])][:GRAPH_DRAW_COUNT]
    if len(samples) < 2:
        c.create_text((x0+x1)/2, (y0+y1)/2, text=(self.graph or {}).get("error", "Нет графика"), fill="#555", width=pw-10)
        return
    amps, mode = _v20_graph_curve(samples)
    p99 = max(1.0, _v20_percentile([a for a in amps if a > 0], 0.99, max(amps or [1.0])))
    gain = min(14.0, max(0.45, (ph*0.74)/p99))
    pts: list[float] = []
    for i, ap in enumerate(amps):
        x = x0 + (i/max(1,len(amps)-1))*pw
        y = baseline_y - float(ap)*gain
        y = max(y0+2, min(y1-2, y))
        pts.extend((x,y))
    if len(pts) >= 4:
        c.create_line(*pts, fill="#111", width=1)
    # Defect/reflector marker from exact metric if available; otherwise strongest visible tail echo.
    mx = my = None
    try:
        r_mm = _v16_safe_float((self.defect or {}).get("defect_r"), 0.0)  # type: ignore[name-defined]
        if r_mm > 0:
            speed = _v16_safe_float((getattr(self,"setting_params",{}) or {}).get("sound_speed"),5900.0)  # type: ignore[name-defined]
            mx = x_by_t10(round(r_mm*20000.0/max(1.0,speed)))
            y_mm = _v16_safe_float((self.defect or {}).get("defect_y"),0.0)  # type: ignore[name-defined]
            ratio = max(0.05,min(0.95,y_mm/r_mm)) if r_mm > 1 and y_mm >= 0 else 0.50
            my = y1 - 10 - ratio*(ph*0.70)
    except Exception:
        pass
    if mx is None or my is None:
        tail_start = max(0, int(len(amps)*0.70))
        idx, a = max(enumerate(amps), key=lambda ia: ia[1] + (35 if ia[0] >= tail_start else 0))
        mx = x0 + (idx/max(1,len(amps)-1))*pw
        my = baseline_y - float(a)*gain
    mx = max(x0+8,min(x1-8,float(mx))); my = max(y0+8,min(y1-8,float(my)))
    c.create_line(mx-8,my,mx+8,my,fill="#222"); c.create_line(mx,my-8,mx,my+8,fill="#222")

try:
    NativeAscanProtocolSheet._draw_native_graph = _v20_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass

# Print preview with manual zoom.  The A4 sheet is always 794x1123 internally;
# the preview scale is only visual.  Actual print uses the fitted A4 canvas.
def _v20_scaled_font(font_desc: Any, scale: float) -> Any:
    try:
        import tkinter.font as tkfont
        if font_desc:
            f = tkfont.Font(font=font_desc)
            fam = f.actual("family") or "Arial"
            size = abs(int(f.actual("size") or 9))
            weight = f.actual("weight") or "normal"
            slant = f.actual("slant") or "roman"
            return (fam, max(4, int(size*scale)), "bold" if weight == "bold" else "normal", "italic" if slant == "italic" else "roman")
    except Exception:
        pass
    return ("Arial", max(4, int(8*scale)))


def _v20_clone_canvas_items(src: tk.Canvas, dst: tk.Canvas, scale: float = 1.0, ox: float = 0.0, oy: float = 0.0) -> None:
    def sc(vals: list[float]) -> list[float]:
        return [ox + vals[i]*scale if i%2==0 else oy + vals[i]*scale for i in range(len(vals))]
    for item in src.find_all():
        try:
            typ = src.type(item)
            coords = [float(v) for v in src.coords(item)]
            if typ == "line":
                dst.create_line(*sc(coords), fill=src.itemcget(item,"fill") or "#111", dash=src.itemcget(item,"dash"), width=max(1, int(float(src.itemcget(item,"width") or 1)*scale)))
            elif typ == "rectangle":
                dst.create_rectangle(*sc(coords), outline=src.itemcget(item,"outline") or "#111", fill=src.itemcget(item,"fill") or "")
            elif typ == "text":
                opts: dict[str, Any] = {
                    "text": src.itemcget(item,"text"), "fill": src.itemcget(item,"fill") or "#111",
                    "anchor": src.itemcget(item,"anchor") or "nw", "font": _v20_scaled_font(src.itemcget(item,"font"), scale)
                }
                try:
                    ws = src.itemcget(item,"width")
                    if ws and float(ws) > 0:
                        opts["width"] = max(1, int(float(ws)*scale))
                except Exception:
                    pass
                xy = sc(coords[:2]) if coords else [ox,oy]
                dst.create_text(xy[0], xy[1], **opts)
            elif typ == "window":
                win_name = src.itemcget(item,"window")
                if win_name and coords:
                    try:
                        child = src.nametowidget(win_name)
                        if isinstance(child, tk.Canvas):
                            _v20_clone_canvas_items(child, dst, scale, ox+coords[0]*scale, oy+coords[1]*scale)
                    except Exception:
                        pass
        except Exception:
            continue

_v19_clone_canvas_items = _v20_clone_canvas_items  # type: ignore[assignment]

def _v20_a4_canvas_from(src: tk.Canvas, owner: tk.Misc, margin: int = 26) -> tk.Canvas:
    try:
        src.update_idletasks()
        cw = int(float(src.cget("width"))); ch = int(float(src.cget("height")))
    except Exception:
        cw, ch = 1040, 1380
    scale = min((V19_A4_W-margin*2)/max(1,cw), (V19_A4_H-margin*2)/max(1,ch), 1.0) * 0.94
    c = tk.Canvas(owner, bg="white", width=V19_A4_W, height=V19_A4_H, highlightthickness=0)
    _v20_clone_canvas_items(src, c, scale, margin, margin)
    return c

_v19_a4_canvas_from = _v20_a4_canvas_from  # type: ignore[assignment]

def _v20_print_preview(owner: tk.Misc, canvas: Optional[tk.Canvas] = None, title: str = "peleng_sheet") -> None:
    try:
        if canvas is None:
            canvas = getattr(owner, "page_canvas", None)
        if not isinstance(canvas, tk.Canvas):
            canvas = _v19_make_report_print_canvas(owner)  # type: ignore[name-defined]
        if not isinstance(canvas, tk.Canvas):
            messagebox.showerror("Печать", "Не найден Canvas листа для печати", parent=owner)
            return
        a4_canvas = canvas if (int(float(canvas.cget("width"))) == V19_A4_W and int(float(canvas.cget("height"))) == V19_A4_H) else _v20_a4_canvas_from(canvas, owner)
        win = tk.Toplevel(owner)
        win.title("Предпросмотр печати A4")
        win.geometry("760x900")
        top = ttk.Frame(win, padding=6); top.pack(fill=tk.X)
        printers = _v17_enum_printers()  # type: ignore[name-defined]
        default_prn = _v17_default_printer()  # type: ignore[name-defined]
        ttk.Label(top, text="Принтер:").pack(side=tk.LEFT, padx=(0,4))
        prn_var = tk.StringVar(value=default_prn or (printers[0] if printers else ""))
        ttk.Combobox(top, textvariable=prn_var, values=printers, width=36, state=("readonly" if printers else "normal")).pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text="Масштаб:").pack(side=tk.LEFT, padx=(12,4))
        zoom_var = tk.StringVar(value="70%")
        zoom = ttk.Combobox(top, textvariable=zoom_var, values=["45%","55%","65%","70%","80%","90%","100%"], width=6, state="readonly")
        zoom.pack(side=tk.LEFT)
        body = tk.Canvas(win, bg="#555", highlightthickness=0)
        vsb = ttk.Scrollbar(win, orient=tk.VERTICAL, command=body.yview)
        hsb = ttk.Scrollbar(win, orient=tk.HORIZONTAL, command=body.xview)
        body.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); vsb.pack(side=tk.RIGHT, fill=tk.Y); hsb.pack(side=tk.BOTTOM, fill=tk.X)
        page_holder = {"page": None}
        def render() -> None:
            try:
                z = float(str(zoom_var.get()).strip().rstrip("%"))/100.0
            except Exception:
                z = 0.70
            body.delete("all")
            page = tk.Canvas(body, bg="white", width=int(V19_A4_W*z), height=int(V19_A4_H*z), bd=1, relief=tk.SOLID, highlightthickness=0)
            body.create_window(14,14,anchor="nw",window=page)
            body.configure(scrollregion=(0,0,int(V19_A4_W*z)+28,int(V19_A4_H*z)+28))
            _v20_clone_canvas_items(a4_canvas, page, z)
            page_holder["page"] = page
        zoom.bind("<<ComboboxSelected>>", lambda _e: render())
        render()
        safe_title = re.sub(r"[^A-Za-z0-9А-Яа-я_.-]+", "_", str(title or "peleng_sheet"))[:80]
        def do_print() -> None:
            import tempfile
            path = os.path.join(tempfile.gettempdir(), f"{safe_title}.ps")
            _v19_save_postscript(a4_canvas, path)  # type: ignore[name-defined]
            try:
                _v17_print_file_to_printer(path, prn_var.get().strip())  # type: ignore[name-defined]
                messagebox.showinfo("Печать", "Задание отправлено в печать", parent=win)
            except Exception as exc:
                # Keep the workflow useful even on systems without pywin32/PostScript handlers.
                try:
                    if os.name == "nt":
                        os.startfile(path)  # type: ignore[attr-defined]
                except Exception:
                    pass
                messagebox.showwarning("Печать", f"Автопечать недоступна. Файл A4 сохранён и открыт для печати вручную:\n{path}\n\nПричина: {exc}", parent=win)
        ttk.Button(top, text="Печать", command=do_print).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text="Закрыть", command=win.destroy).pack(side=tk.RIGHT, padx=4)
    except Exception as exc:
        messagebox.showerror("Печать", str(exc), parent=owner)

_v17_print_preview = _v20_print_preview  # type: ignore[assignment]
_v18_print_preview = _v20_print_preview  # type: ignore[assignment]
_v19_print_preview = _v20_print_preview  # type: ignore[assignment]
try:
    _v17_wrap_buttons(NativeReportSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(NativeAscanProtocolSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(SettingDetail)  # type: ignore[name-defined]
except Exception:
    pass

# More compact setting sheet on-screen as well.  It keeps the same content, but
# the preview/print scaler now has less to shrink.
try:
    NativeSettingSheet.PAGE_W = 920  # type: ignore[name-defined]
    NativeSettingSheet.PAGE_H = 1180  # type: ignore[name-defined]
    SettingDetail.PAGE_W = 920  # type: ignore[name-defined]
    SettingDetail.PAGE_H = 1180  # type: ignore[name-defined]
except Exception:
    pass


# ---------------------------------------------------------------------------
# v21 compact setting sheet, graph gates/defect logic, direct printer helper
# ---------------------------------------------------------------------------
# User-facing goals:
#   * setting sheet is compact on screen/A4 but keeps the native layout;
#   * graph uses only ВС1/ВС2 dashed gates; no extra ВРЧ stripe clutter;
#   * defect marker is searched only inside ВС1/ВС2 intervals;
#   * printing tries direct Windows GDI printer output first (pywin32), not only PS.

V21_VERSION = "v21 compact setting print graph gates"


def _v21_safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(str(x).replace(',', '.'))
    except Exception:
        return default


def _v21_graph_from_record(raw: bytes) -> dict[str, Any]:
    """Return a graph even when the old scorer dislikes the block.

    Native RESULTS2/4000 records used on this device keep the visible graph in
    the final 0xF4 bytes most often.  Several previous versions rejected this
    block when it looked like a DC plateau; for display that is worse than
    drawing a low-contrast trace.  Prefer tail-0xF4 for 4000/6000-sized records,
    then fall back to the original scorer.
    """
    if not raw or len(raw) < GRAPH_COPY_LEN:
        return {"error": "Нет полного блока графика 0xF4"}
    candidates = []
    for off in (len(raw) - GRAPH_COPY_LEN, GRAPH_OFF, 0x1B8, 0x1C5, 0x1D5, 0x1E5):
        if 0 <= int(off) <= len(raw) - GRAPH_COPY_LEN and int(off) not in candidates:
            candidates.append(int(off))
    # Prefer blocks with non-trivial noise/echo, but never reject the tail block.
    def score(off: int) -> float:
        block = list(raw[off:off+GRAPH_COPY_LEN])[:GRAPH_DRAW_COUNT]
        if not block:
            return -1.0
        amp = max(block) - min(block)
        tail = block[int(len(block)*0.70):]
        tail_amp = (max(tail)-min(tail)) if tail else 0
        # small bonus for tail candidate because live 4000 captures use it.
        return amp + 0.7*tail_amp + (15 if off == len(raw)-GRAPH_COPY_LEN else 0)
    off = max(candidates, key=score)
    block = list(raw[off:off+GRAPH_COPY_LEN])
    samples = block[:GRAPH_DRAW_COUNT]
    return {
        "offset": off,
        "copy_len": GRAPH_COPY_LEN,
        "draw_count": len(samples),
        "baseline": GRAPH_BASELINE,
        "raw_block": block,
        "samples": samples,
        "min_sample": min(samples) if samples else None,
        "max_sample": max(samples) if samples else None,
        "source": "v21_tail_or_scored",
    }


def _v21_decode_graph(self: NativeAscanProtocolSheet) -> dict[str, Any]:  # type: ignore[name-defined]
    """Graph source chooser: selected raw first, then linked/pair records."""
    candidates: list[tuple[str, int, bytes]] = []
    try:
        if getattr(self, 'raw', b''):
            candidates.append(("selected", int(getattr(self, 'addr', 0)), bytes(self.raw)))
    except Exception:
        pass
    try:
        for a in [getattr(self, 'graph_addr', 0), 4000 + (int(getattr(self,'addr',0)) % 1000), 6000 + (int(getattr(self,'addr',0)) % 1000)]:
            if not a:
                continue
            rr = self.db.get_raw_by_addr(int(a))
            if rr:
                candidates.append((f"addr:{a}", int(a), bytes(rr['raw'])))
    except Exception:
        pass
    # All loaded RESULT-like records with same setting_no are last resort.
    try:
        sn = int(getattr(self, 'setting_no', 0) or 0)
        cur = self.db.conn.execute("SELECT address, raw FROM raw_records WHERE address BETWEEN 4000 AND 6999 ORDER BY address")
        for row in cur.fetchall():
            raw = bytes(row['raw'])
            if len(raw) >= GRAPH_COPY_LEN and (not sn or protocol_setting_no_643(raw) == sn):
                candidates.append((f"loaded:{row['address']}", int(row['address']), raw))
    except Exception:
        pass
    # Deduplicate and pick first full-looking 4000/6000 source with graph.
    seen=set(); best=None; best_score=-1e9
    for name, addr, raw in candidates:
        key=(addr, len(raw), raw[:8])
        if key in seen:
            continue
        seen.add(key)
        if len(raw) < GRAPH_COPY_LEN or len(raw) == LEN_SHORTPROT2:
            continue
        g=_v21_graph_from_record(raw)
        if 'samples' not in g:
            continue
        samples=[int(s)&0xFF for s in g.get('samples', [])]
        if not samples:
            continue
        # Prefer selected/full 4000, visible dynamic range, and tail echo.
        amp=max(samples)-min(samples)
        tail=samples[int(len(samples)*0.70):]
        tail_amp=(max(tail)-min(tail)) if tail else 0
        sc=amp+tail_amp
        if name=='selected': sc += 80
        if 4000 <= addr <= 4999: sc += 30
        if 6000 <= addr <= 6999 and len(raw) >= LEN_ASCAN_6000: sc += 20
        if sc > best_score:
            best_score=sc; best=(name, addr, raw, g)
    if best:
        try:
            self.graph_source_name, self.graph_source_addr, self.graph_source_raw = best[0], best[1], best[2]
        except Exception:
            pass
        return best[3]
    return {"error": "Нет полного блока графика 0xF4. Получите протокол и связанный 4000/6000 адрес заново."}


def _v21_graph_amplitudes(samples: list[int]) -> tuple[list[float], str]:
    """Stable visible envelope: no inversion plateau, no blank line.

    Native graph is an envelope around a bottom baseline.  For captures where
    the whole block is shifted up/down, subtract the local floor and amplify the
    remaining echo.  Choose polarity by visible energy inside the tail and ВС
    zones, not by the whole DC level.
    """
    if not samples:
        return [], 'empty'
    vals = [float(s) for s in samples]
    # Two physically plausible directions.  Use robust floor removal to avoid
    # turning the DC component into a full-height plateau.
    cand=[]
    for arr,name in (([v-GRAPH_BASELINE for v in vals], 'sample-0x8C'), ([GRAPH_BASELINE-v for v in vals], '0x8C-sample')):
        sorted_arr=sorted(arr)
        floor=sorted_arr[max(0, min(len(sorted_arr)-1, int(len(sorted_arr)*0.08)))] if sorted_arr else 0
        dyn=[max(0.0, a-floor) for a in arr]
        p50=sorted(dyn)[len(dyn)//2] if dyn else 0
        peak=max(dyn or [0])
        tail=max(dyn[int(len(dyn)*0.70):] or [0])
        # Penalize plateau, reward peaks/tail.
        score=peak + 1.5*tail - 1.2*p50
        cand.append((score,dyn,name))
    score,dyn,name=max(cand,key=lambda t:t[0])
    # If almost flat, draw small deviations around median so the user still sees
    # the raw trace/noise instead of an empty rectangle.
    if max(dyn or [0]) < 2:
        med=sorted(vals)[len(vals)//2]
        dyn=[abs(v-med) for v in vals]
        name='abs-median'
    return dyn,name


def _v21_draw_native_graph(self: NativeAscanProtocolSheet) -> None:  # type: ignore[name-defined]
    c = self.graph_canvas
    c.delete('all')
    x0,y0=12,10
    pw,ph=280,200
    x1,y1=x0+pw,y0+ph
    c.create_rectangle(x0,y0,x1,y1,outline='#222')
    for i in range(1,10):
        x=x0+pw*i/10
        c.create_line(x,y0,x,y1,fill='#d4d4d4',dash=(1,7))
    for i in range(1,7):
        y=y0+ph*i/7
        c.create_line(x0,y,x1,y,fill='#d4d4d4',dash=(1,7))
    baseline_y=y1-18
    c.create_line(x0,baseline_y,x1,baseline_y,fill='#777')

    zone = _v13_zone_values(self) if '_v13_zone_values' in globals() else {}  # type: ignore[name-defined]
    try:
        duration=int(zone.get('duration_t10') or (getattr(self,'setting_params',{}) or {}).get('duration_t10') or 7920)
    except Exception:
        duration=7920
    duration=max(1,duration)
    def x_by_t10(v: Any) -> float:
        try: rx=float(v or 0)
        except Exception: rx=0.0
        return max(x0,min(x1,x0+(rx/duration)*pw))

    # Only ВС1/ВС2 dashed gates.  Defect search is allowed only inside these.
    gate_ranges=[]
    def draw_gate(a: Any,b: Any,label: str) -> None:
        try: aa,bb=int(a or 0),int(b or 0)
        except Exception: return
        if aa<=0 and bb<=0: return
        if bb<aa: aa,bb=bb,aa
        xa,xb=x_by_t10(aa),x_by_t10(bb)
        gate_ranges.append((xa,xb,aa,bb,label))
        c.create_line(xa,y0+2,xa,y1-2,fill='#222',dash=(3,4),width=1)
        c.create_line(xb,y0+2,xb,y1-2,fill='#222',dash=(3,4),width=1)
        c.create_text((xa+xb)/2,y0+12,text=label,fill='#222',font=('Arial',8,'bold'))
    draw_gate(zone.get('vs1_start_raw'), zone.get('vs1_end_raw'), 'ВС1')
    draw_gate(zone.get('vs2_start_raw'), zone.get('vs2_end_raw'), 'ВС2')

    if 'samples' not in self.graph:
        c.create_text((x0+x1)/2,(y0+y1)/2,text=self.graph.get('error','Нет графика'),fill='#555',width=pw-20)
        return
    samples=[int(s)&0xFF for s in (self.graph.get('samples') or [])][:GRAPH_DRAW_COUNT]
    if len(samples)<2:
        c.create_text((x0+x1)/2,(y0+y1)/2,text='Нет точек графика',fill='#555')
        return
    amps,mode=_v21_graph_amplitudes(samples)
    positive=[a for a in amps if a>0]
    positive_sorted=sorted(positive)
    p98=positive_sorted[min(len(positive_sorted)-1,int(len(positive_sorted)*0.98))] if positive_sorted else 1.0
    if p98 < 1: p98=max(positive or [1.0])
    gain=max(0.7,min(12.0,(ph*0.72)/max(1.0,p98)))
    pts=[]
    for i,a in enumerate(amps):
        x=x0+(i/max(1,len(amps)-1))*pw
        y=baseline_y-float(a)*gain
        y=max(y0+2,min(y1-2,y))
        pts.extend((x,y))
    if len(pts)>=4:
        c.create_line(*pts,fill='#111',width=1)

    # Defect/reflection marker: ONLY inside ВС1/ВС2.  If descriptor R is outside
    # those zones or zero, use strongest visible peak inside the gates.  If no
    # gate contains a peak, draw no fake defect marker.
    marker=None
    try:
        r_mm=_v21_safe_float((self.defect or {}).get('defect_r'),0.0)
        speed=_v21_safe_float((getattr(self,'setting_params',{}) or {}).get('sound_speed'),5900.0)
        if r_mm>0 and speed>0:
            t10=round(r_mm*20000.0/max(1.0,speed))
            mx=x_by_t10(t10)
            for xa,xb,aa,bb,_label in gate_ranges:
                if xa-1 <= mx <= xb+1:
                    y_mm=_v21_safe_float((self.defect or {}).get('defect_y'),0.0)
                    ratio=max(0.05,min(0.95,y_mm/max(1.0,r_mm))) if y_mm>=0 else 0.5
                    marker=(mx, y1-10-ratio*(ph*0.70))
                    break
    except Exception:
        marker=None
    if marker is None and gate_ranges:
        best_i=None; best_a=-1.0
        for i,a in enumerate(amps):
            x=x0+(i/max(1,len(amps)-1))*pw
            if any(xa-1 <= x <= xb+1 for xa,xb,_,__,___ in gate_ranges):
                if a>best_a:
                    best_a=float(a); best_i=i
        if best_i is not None and best_a>0:
            mx=x0+(best_i/max(1,len(amps)-1))*pw
            my=baseline_y-best_a*gain
            marker=(mx,my)
    if marker:
        mx=max(x0+8,min(x1-8,float(marker[0]))); my=max(y0+8,min(y1-8,float(marker[1])))
        c.create_line(mx-8,my,mx+8,my,fill='#222')
        c.create_line(mx,my-8,mx,my+8,fill='#222')


def _v21_setting_draw_compact(self: SettingDetail, c: tk.Canvas) -> None:  # type: ignore[name-defined]
    """Compact native-like setting sheet that fits on screen and A4."""
    p = self.params or {}
    dev, ver = self._header_device_version() if hasattr(self, '_header_device_version') else ('','')
    num = p.get('setting_no') or (self.addr - 1000 if 1000 <= self.addr <= 1999 else self.addr)
    date = self._p('date','') if hasattr(self,'_p') else ''
    time_s = self._p('time','') if hasattr(self,'_p') else ''
    operator_code = self._p('operator_code','00') if hasattr(self,'_p') else '00'
    c.create_text(46,34,text=f"П А Р А М Е Т Р Ы   Н А С Т Р О Й К И   №{num}",anchor='nw',font=('Arial',11,'bold'))
    c.create_text(46,58,text=f"дефектоскоп УД2-102 № {dev}, {date} {time_s}, Версия {ver}",anchor='nw',font=('Arial',8))
    def t(x,y,s,size=8,bold=False,width=None):
        opts={'text':str(s or ''),'anchor':'nw','font':('Arial',size,'bold' if bold else 'normal'),'fill':'#111'}
        if width: opts['width']=width
        c.create_text(x,y,**opts)
    def row(x,y,l,v,vx=180,b=False):
        t(x,y,l,8); t(x+vx,y,_v15_clean(v),8,bold=b,width=300)
    def title(x,y,s,w=250):
        t(x,y,s,9,True); c.create_line(x,y+15,x+w,y+15,fill='#222')
    row(46,120,'Типовой вариант',p.get('typevar_code') or p.get('typevar') or '',vx=185)
    row(520,120,'Шифр оператора',operator_code,vx=170)
    t(300,176,'Р Е Г У Л И Р У Е М Ы Е   П А Р А М Е Т Р Ы',10,True); c.create_line(298,193,670,193,fill='#222')
    y=232
    for l,k in [('Частота УЗК, МГц','freq_mhz'),('Скорость УЗК, м/с','sound_speed'),('Толщина, мм','thickness_mm'),('Ампл. зонд.','amplitude_probe'),('Отсечка, %','cutoff_pct'),('Блокировка','blocking')]:
        row(52,y,l,self._p(k) if hasattr(self,'_p') else p.get(k)); y+=20
    y+=14; title(62,y,'П Э П',95); y+=26
    for l,k in [('№ ПЭП','probe_no'),('вкл. ПЭП','probe_enabled'),('Угол ввода, град.','angle_deg'),('Время в ПЭП, мкс','probe_time_us')]:
        row(52,y,l,self._p(k) if hasattr(self,'_p') else p.get(k)); y+=20
    y+=14; title(62,y,'Ч у в с т в и т е л ь н о с т ь',220); y+=26
    for l,k in [('Усиление, дБ','gain_db'),('Треб. чувст., дБ','required_sens_db'),('Факт. чувст., дБ','actual_sens_db'),('Доп. усиление, дБ','extra_gain_db'),('Вкл. доп. усиления','extra_gain_enabled')]:
        row(52,y,l,self._p(k) if hasattr(self,'_p') else p.get(k)); y+=20
    y+=14; title(62,y,'Р а з в е р т к а',150); y+=26
    for l,k in [('Тип','sweep_type'),('Длительность','sweep_duration'),('Задержка','sweep_delay'),('W-развертка','w_sweep_enabled'),('Огибающая','envelope_enabled')]:
        row(52,y,l,self._p(k) if hasattr(self,'_p') else p.get(k),vx=185); y+=20
    y+=14; title(62,y,'Л у п а',90); y+=26
    row(52,y,'Вкл.',self._p('magnifier_enabled') if hasattr(self,'_p') else p.get('magnifier_enabled')); y+=20
    row(52,y,'Вид',self._p('magnifier_type') if hasattr(self,'_p') else p.get('magnifier_type'))
    x=520; y=250
    title(x,y-24,'Н а с т р о й к а   п о   С О',270)
    for l,k in [('Нач. зоны ВС','so_start'),('Конец зоны ВС','so_end')]: row(x,y,l,self._p(k),vx=170); y+=20
    y+=20; title(x,y-24,'З о н а   В С 1',165)
    for l,k in [('Начало','vs1_start'),('Конец','vs1_end'),('Метод','vs1_method'),('Порог, %','vs1_threshold_pct')]: row(x,y,l,self._p(k),vx=170); y+=20
    y+=20; title(x,y-24,'З о н а   В С 2',165)
    for l,k in [('Начало','vs2_start'),('Конец','vs2_end'),('Метод','vs2_method'),('Порог, %','vs2_threshold_pct')]: row(x,y,l,self._p(k),vx=170); y+=20
    y+=20; title(x,y-24,'А Р У',70)
    for l,k in [('Вкл.','aru_enabled'),('Начало','aru_start'),('Конец','aru_end')]: row(x,y,l,self._p(k),vx=170); y+=20
    y+=20; title(x,y-24,'В Р Ч',70)
    for l,k in [('Тип ВРЧ','vrch_type'),('Индикация','vrch_indication'),('Начало','vrch_start'),('Конец','vrch_end'),('Амплитуда, дБ','vrch_amp_db'),('Форма','vrch_shape'),('До ВРЧ, дБ','before_vrch_db'),('После ВРЧ, дБ','after_vrch_db')]: row(x,y,l,self._p(k),vx=170); y+=20
    t(295,900,'Ф И К С И Р О В А Н Н Ы Е   П А Р А М Е Т Р Ы',10,True); c.create_line(293,918,690,918,fill='#222')
    row(52,940,'Пер. зондирования',self._p('probing_period')); row(52,960,'Порог, %',self._p('fixed_threshold_pct'))
    row(520,940,'Част. зонд., Гц',self._p('probing_freq_hz'),vx=170); row(520,960,'Доп. метка',self._p('additional_mark'),vx=170)


def _v21_try_print_direct_gdi(src_canvas: tk.Canvas, printer: str, title: str = 'Peleng') -> bool:
    """Try real Windows printer output via pywin32 GDI.

    This avoids relying on PostScript file associations.  It prints text/lines/
    rectangles from the Canvas directly to the selected printer DC, scaled to A4
    printable area.  If pywin32 is absent it returns False and caller falls back.
    """
    if os.name != 'nt':
        return False
    try:
        import win32ui  # type: ignore
        import win32con  # type: ignore
    except Exception:
        return False
    try:
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer or None)
        dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
        dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY)
        printable_w = dc.GetDeviceCaps(win32con.HORZRES)
        printable_h = dc.GetDeviceCaps(win32con.VERTRES)
        # A4 canvas base 794x1123; fit to printable region.
        try:
            cw = int(float(src_canvas.cget('width'))); ch = int(float(src_canvas.cget('height')))
        except Exception:
            cw,ch = V19_A4_W,V19_A4_H
        scale = min(printable_w/max(1,cw), printable_h/max(1,ch)) * 0.94
        ox = int((printable_w - cw*scale)/2)
        oy = int((printable_h - ch*scale)/2)
        dc.StartDoc(str(title or 'Peleng'))
        dc.StartPage()
        def pt(x,y): return int(ox + float(x)*scale), int(oy + float(y)*scale)
        # Fonts cache by size/bold.
        fonts={}
        def get_font(font_desc):
            key=('Arial',9,'normal')
            try:
                import tkinter.font as tkfont
                f=tkfont.Font(font=font_desc)
                key=(f.actual('family') or 'Arial', abs(int(f.actual('size') or 9)), f.actual('weight') or 'normal')
            except Exception:
                pass
            if key not in fonts:
                height = -max(6, int(key[1] * dpi_y / 72 * scale))
                weight = 700 if key[2] == 'bold' else 400
                fonts[key] = win32ui.CreateFont({'name': key[0], 'height': height, 'weight': weight})
            return fonts[key]
        for item in src_canvas.find_all():
            typ=src_canvas.type(item); coords=src_canvas.coords(item)
            if typ == 'line' and len(coords) >= 4:
                x,y=pt(coords[0],coords[1]); dc.MoveTo((x,y))
                for i in range(2,len(coords),2):
                    x,y=pt(coords[i],coords[i+1]); dc.LineTo((x,y))
            elif typ == 'rectangle' and len(coords) >= 4:
                x0,y0=pt(coords[0],coords[1]); x1,y1=pt(coords[2],coords[3]); dc.Rectangle((x0,y0,x1,y1))
            elif typ == 'text' and len(coords) >= 2:
                font=get_font(src_canvas.itemcget(item,'font'))
                old=dc.SelectObject(font)
                x,y=pt(coords[0],coords[1])
                text=src_canvas.itemcget(item,'text') or ''
                dc.TextOut(x,y,text)
                try: dc.SelectObject(old)
                except Exception: pass
        dc.EndPage(); dc.EndDoc(); dc.DeleteDC()
        return True
    except Exception:
        try:
            dc.AbortDoc(); dc.DeleteDC()
        except Exception:
            pass
        return False


def _v21_print_preview(owner: tk.Misc, canvas: Optional[tk.Canvas] = None, title: str = 'peleng_sheet') -> None:
    # Reuse v20 preview but replace print command with direct GDI first.
    try:
        if canvas is None:
            canvas = getattr(owner, 'page_canvas', None)
        if not isinstance(canvas, tk.Canvas):
            canvas = _v19_make_report_print_canvas(owner)  # type: ignore[name-defined]
        if not isinstance(canvas, tk.Canvas):
            messagebox.showerror('Печать','Не найден Canvas листа для печати',parent=owner); return
        a4_canvas = canvas if (int(float(canvas.cget('width'))) == V19_A4_W and int(float(canvas.cget('height'))) == V19_A4_H) else _v20_a4_canvas_from(canvas, owner)  # type: ignore[name-defined]
        win=tk.Toplevel(owner); win.title('Предпросмотр печати A4'); win.geometry('800x900')
        top=ttk.Frame(win,padding=6); top.pack(fill=tk.X)
        printers=_v17_enum_printers()  # type: ignore[name-defined]
        default_prn=_v17_default_printer()  # type: ignore[name-defined]
        ttk.Label(top,text='Принтер:').pack(side=tk.LEFT,padx=(0,4))
        prn_var=tk.StringVar(value=default_prn or (printers[0] if printers else ''))
        ttk.Combobox(top,textvariable=prn_var,values=printers,width=38,state=('readonly' if printers else 'normal')).pack(side=tk.LEFT,padx=4)
        ttk.Label(top,text='Масштаб:').pack(side=tk.LEFT,padx=(12,4))
        zoom_var=tk.StringVar(value='70%')
        zoom=ttk.Combobox(top,textvariable=zoom_var,values=['45%','55%','65%','70%','80%','90%','100%'],width=6,state='readonly'); zoom.pack(side=tk.LEFT)
        body=tk.Canvas(win,bg='#555',highlightthickness=0); vsb=ttk.Scrollbar(win,orient=tk.VERTICAL,command=body.yview); hsb=ttk.Scrollbar(win,orient=tk.HORIZONTAL,command=body.xview)
        body.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set); body.pack(side=tk.LEFT,fill=tk.BOTH,expand=True); vsb.pack(side=tk.RIGHT,fill=tk.Y); hsb.pack(side=tk.BOTTOM,fill=tk.X)
        def render(*_):
            try: z=float(zoom_var.get().rstrip('%'))/100.0
            except Exception: z=0.70
            body.delete('all'); page=tk.Canvas(body,bg='white',width=int(V19_A4_W*z),height=int(V19_A4_H*z),bd=1,relief=tk.SOLID,highlightthickness=0)
            body.create_window(14,14,anchor='nw',window=page); body.configure(scrollregion=(0,0,int(V19_A4_W*z)+28,int(V19_A4_H*z)+28))
            _v20_clone_canvas_items(a4_canvas,page,z)  # type: ignore[name-defined]
        zoom.bind('<<ComboboxSelected>>',render); render()
        safe_title=re.sub(r'[^A-Za-z0-9А-Яа-я_.-]+','_',str(title or 'peleng_sheet'))[:80]
        def do_print():
            prn=prn_var.get().strip()
            if _v21_try_print_direct_gdi(a4_canvas, prn, safe_title):
                messagebox.showinfo('Печать','Задание отправлено на принтер',parent=win); return
            # fallback: PS for systems without pywin32
            import tempfile
            path=os.path.join(tempfile.gettempdir(),f'{safe_title}.ps')
            _v19_save_postscript(a4_canvas,path)  # type: ignore[name-defined]
            try:
                _v17_print_file_to_printer(path, prn)  # type: ignore[name-defined]
                messagebox.showinfo('Печать','Задание отправлено в печать',parent=win)
            except Exception as exc:
                messagebox.showwarning('Печать',f'Автопечать недоступна. Установите pywin32 для прямой печати или распечатайте файл вручную:\n{path}\n\nПричина: {exc}',parent=win)
        ttk.Button(top,text='Печать',command=do_print).pack(side=tk.LEFT,padx=8)
        ttk.Button(top,text='Закрыть',command=win.destroy).pack(side=tk.RIGHT,padx=4)
    except Exception as exc:
        messagebox.showerror('Печать',str(exc),parent=owner)

# Apply v21 patches.
try:
    NativeAscanProtocolSheet._decode_graph = _v21_decode_graph  # type: ignore[name-defined]
    NativeAscanProtocolSheet._draw_native_graph = _v21_draw_native_graph  # type: ignore[name-defined]
except Exception:
    pass
try:
    NativeSettingSheet.PAGE_W = 820  # type: ignore[name-defined]
    NativeSettingSheet.PAGE_H = 1040  # type: ignore[name-defined]
    SettingDetail.PAGE_W = 820  # type: ignore[name-defined]
    SettingDetail.PAGE_H = 1040  # type: ignore[name-defined]
    NativeSettingSheet._draw = _v21_setting_draw_compact  # type: ignore[name-defined]
    SettingDetail._draw = _v21_setting_draw_compact  # type: ignore[name-defined]
except Exception:
    pass
try:
    _v17_print_preview = _v21_print_preview  # type: ignore[assignment]
    _v18_print_preview = _v21_print_preview  # type: ignore[assignment]
    _v19_print_preview = _v21_print_preview  # type: ignore[assignment]
    _v20_print_preview = _v21_print_preview  # type: ignore[assignment]
    _v17_wrap_buttons(NativeReportSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(NativeAscanProtocolSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(SettingDetail)  # type: ignore[name-defined]
except Exception:
    pass


# ---------------------------------------------------------------------------
# v22: final A4 bitmap printing, compact settings window, graph gate cleanup
# ---------------------------------------------------------------------------
APP_BUILD_VERSION = "v22 A4 bitmap print + compact settings + graph gates"

# Native GUI pages are built in Tk logical pixels.  For printing we render the
# fitted A4 canvas into a bitmap and send that bitmap to the Windows printer DC.
# This avoids the previous direct-GDI text-size problem where printer fonts were
# much larger than the A4 preview.

def _v22_canvas_to_image(src: tk.Canvas, scale: float = 2.0):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:  # pragma: no cover - runtime dependency on Windows
        raise RuntimeError("Для прямой печати нужен Pillow: python -m pip install pillow") from exc
    try:
        src.update_idletasks()
    except Exception:
        pass
    try:
        w = max(1, int(float(src.cget('width'))))
        h = max(1, int(float(src.cget('height'))))
    except Exception:
        w, h = V19_A4_W, V19_A4_H
    W, H = int(w * scale), int(h * scale)
    img = Image.new('RGB', (W, H), 'white')
    draw = ImageDraw.Draw(img)

    def pts(coords):
        return [(float(coords[i]) * scale, float(coords[i+1]) * scale) for i in range(0, len(coords)-1, 2)]

    def color(value: str, default='black'):
        v = (value or '').strip()
        if not v:
            return default
        # Tk may report system colors; fall back to black/white.
        if v.startswith('#'):
            return v
        if v.lower() in ('black', 'white', 'gray', 'grey'):
            return v
        return default

    font_cache = {}
    def get_font(font_desc, factor: float = 1.0):
        key = (str(font_desc), factor)
        if key in font_cache:
            return font_cache[key]
        family = 'arial'
        size = 9
        weight = 'normal'
        try:
            import tkinter.font as tkfont
            f = tkfont.Font(font=font_desc)
            family = f.actual('family') or 'Arial'
            size = abs(int(f.actual('size') or 9))
            weight = f.actual('weight') or 'normal'
        except Exception:
            try:
                parts = str(font_desc or '').split()
                for p in parts:
                    if p.lstrip('-').isdigit():
                        size = abs(int(p)); break
                if 'bold' in str(font_desc).lower(): weight = 'bold'
            except Exception:
                pass
        px = max(6, int(size * scale * factor))
        candidates = []
        if os.name == 'nt':
            base = os.environ.get('WINDIR', r'C:\Windows')
            candidates += [
                os.path.join(base, 'Fonts', 'arialbd.ttf' if weight == 'bold' else 'arial.ttf'),
                os.path.join(base, 'Fonts', 'calibrib.ttf' if weight == 'bold' else 'calibri.ttf'),
            ]
        candidates += [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if weight == 'bold' else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if weight == 'bold' else '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
        ]
        font = None
        for p in candidates:
            try:
                if os.path.exists(p):
                    font = ImageFont.truetype(p, px)
                    break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()
        font_cache[key] = font
        return font

    def draw_wrapped_text(x, y, text, font, fill, width_px=None):
        text = str(text or '')
        if not width_px or width_px <= 0:
            draw.text((x, y), text, font=font, fill=fill)
            return
        # Simple word wrap for long fields; keeps A4 print legible.
        words = text.split(' ')
        lines, cur = [], ''
        for word in words:
            test = (cur + ' ' + word).strip()
            try:
                bbox = draw.textbbox((0, 0), test, font=font)
                tw = bbox[2] - bbox[0]
            except Exception:
                tw = len(test) * 7
            if tw <= width_px or not cur:
                cur = test
            else:
                lines.append(cur); cur = word
        if cur:
            lines.append(cur)
        line_h = max(8, int((getattr(font, 'size', 9) or 9) * 1.15))
        for i, line in enumerate(lines[:4]):
            draw.text((x, y + i * line_h), line, font=font, fill=fill)

    for item in src.find_all():
        try:
            typ = src.type(item)
            coords = [float(v) for v in src.coords(item)]
            if typ == 'line' and len(coords) >= 4:
                p = pts(coords)
                dash = src.itemcget(item, 'dash')
                fill = color(src.itemcget(item, 'fill'), '#111')
                width = max(1, int(float(src.itemcget(item, 'width') or 1) * scale))
                if dash:
                    # PIL dashed polyline helper.
                    for a, b in zip(p, p[1:]):
                        x0, y0 = a; x1, y1 = b
                        dx, dy = x1-x0, y1-y0
                        dist = max(1.0, (dx*dx + dy*dy) ** 0.5)
                        step = 8 * scale
                        t = 0.0
                        on = True
                        while t < dist:
                            t2 = min(dist, t + step)
                            if on:
                                draw.line((x0 + dx*t/dist, y0 + dy*t/dist, x0 + dx*t2/dist, y0 + dy*t2/dist), fill=fill, width=width)
                            on = not on
                            t += step
                else:
                    draw.line(p, fill=fill, width=width)
            elif typ == 'rectangle' and len(coords) >= 4:
                x0, y0, x1, y1 = [v * scale for v in coords[:4]]
                outline = color(src.itemcget(item, 'outline'), '#111')
                fillv = src.itemcget(item, 'fill') or None
                draw.rectangle((x0, y0, x1, y1), outline=outline, fill=(color(fillv, 'white') if fillv else None), width=max(1, int(scale)))
            elif typ == 'text' and len(coords) >= 2:
                x, y = coords[0] * scale, coords[1] * scale
                font = get_font(src.itemcget(item, 'font'), 0.82)
                fill = color(src.itemcget(item, 'fill'), '#111')
                try:
                    width_px = float(src.itemcget(item, 'width') or 0) * scale
                except Exception:
                    width_px = 0
                draw_wrapped_text(x, y, src.itemcget(item, 'text'), font, fill, width_px)
            elif typ == 'window' and len(coords) >= 2:
                # Nested graph canvases should already be cloned into the A4 canvas
                # by _v20_a4_canvas_from.  If a nested canvas remains, render it here.
                win_name = src.itemcget(item, 'window')
                if win_name:
                    try:
                        child = src.nametowidget(win_name)
                        if isinstance(child, tk.Canvas):
                            ch_img = _v22_canvas_to_image(child, scale)
                            img.paste(ch_img, (int(coords[0]*scale), int(coords[1]*scale)))
                    except Exception:
                        pass
        except Exception:
            continue
    return img


def _v22_print_canvas_bitmap(src_canvas: tk.Canvas, printer: str, title: str = 'Peleng') -> bool:
    if os.name != 'nt':
        return False
    try:
        from PIL import ImageWin
        import win32ui  # type: ignore
        import win32con  # type: ignore
    except Exception:
        return False
    try:
        img = _v22_canvas_to_image(src_canvas, scale=2.0)
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer or None)
        printable_w = dc.GetDeviceCaps(win32con.HORZRES)
        printable_h = dc.GetDeviceCaps(win32con.VERTRES)
        # Fit the A4 image into the printer printable region.
        iw, ih = img.size
        scale = min(printable_w / iw, printable_h / ih) * 0.98
        out_w, out_h = int(iw * scale), int(ih * scale)
        ox = int((printable_w - out_w) / 2)
        oy = int((printable_h - out_h) / 2)
        dc.StartDoc(str(title or 'Peleng'))
        dc.StartPage()
        dib = ImageWin.Dib(img)
        dib.draw(dc.GetHandleOutput(), (ox, oy, ox + out_w, oy + out_h))
        dc.EndPage()
        dc.EndDoc()
        dc.DeleteDC()
        return True
    except Exception:
        try:
            dc.AbortDoc(); dc.DeleteDC()
        except Exception:
            pass
        return False


# Compact native-like setting window.  The page is narrower and the window no
# longer starts at 1080px wide, but the original two-column structure is kept.
def _v22_setting_init(self: Any, master: tk.Misc, row: sqlite3.Row, raw: bytes):
    tk.Toplevel.__init__(self, master)
    self.master_app = master
    self.row = row
    self.raw = bytes(raw or b'')
    try:
        self.addr = int(row['address'])
    except Exception:
        self.addr = 0
    try:
        self.params = decode_nastr2_params_643(self.raw, self.addr)
    except Exception as exc:
        self.params = {'error': str(exc)}
    self.title('Настройка')
    self.geometry('860x720')
    self.minsize(720, 560)
    self._build()


def _v22_setting_build(self: Any) -> None:
    top = tk.Frame(self, bg='#efefef', bd=1, relief=tk.GROOVE)
    top.pack(fill=tk.X)
    for txt in ('Печать', 'Сохранить', 'Настройка'):
        tk.Button(top, text=txt, width=12, command=lambda: None).pack(side=tk.LEFT, padx=4, pady=5)
    outer = tk.Canvas(self, bg='#333333', highlightthickness=0)
    vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=outer.yview)
    hsb = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=outer.xview)
    outer.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    hsb.pack(side=tk.BOTTOM, fill=tk.X)
    page = tk.Canvas(outer, bg='white', width=self.PAGE_W, height=self.PAGE_H, bd=1, relief=tk.SOLID, highlightthickness=0)
    outer.create_window(10, 10, anchor='nw', window=page)
    outer.configure(scrollregion=(0, 0, self.PAGE_W + 20, self.PAGE_H + 20))
    self.page_canvas = page
    self._draw(page)
    self.after(80, lambda: outer.yview_moveto(0.0))


def _v22_setting_draw(self: Any, c: tk.Canvas) -> None:
    c.delete('all')
    p = getattr(self, 'params', {}) or {}
    def val(k: str, default: str = '-') -> str:
        try:
            if hasattr(self, '_p'):
                return _v15_clean(self._p(k, default), default)  # type: ignore[name-defined]
        except Exception:
            pass
        return _v15_clean(p.get(k), default)  # type: ignore[name-defined]
    def t(x, y, text, size=7, bold=False, width=None, anchor='nw'):
        c.create_text(x, y, text=str(text or ''), anchor=anchor, fill='#111', font=('Arial', size, 'bold' if bold else 'normal'), width=width)
    def line_title(x, y, text, w=160):
        t(x, y, text, 8, True); c.create_line(x, y+14, x+w, y+14, fill='#222')
    def row(x, y, label, value, vx=150, bold=False, width=240):
        t(x, y, label, 7); t(x+vx, y, _v15_clean(value), 7, bold, width=width)  # type: ignore[name-defined]
    try:
        dev, ver = self._header_device_version()
    except Exception:
        dev = ver = ''
    num = p.get('setting_no') or (getattr(self, 'addr', 0) - 1000 if 1000 <= getattr(self, 'addr', 0) <= 1999 else getattr(self, 'addr', 0))
    t(38, 32, f'П А Р А М Е Т Р Ы   Н А С Т Р О Й К И   №{num}', 11, True)
    t(38, 58, f"дефектоскоп УД2-102 № {dev}, {val('date','')} {val('time','')}, Версия {ver}", 8)
    row(42, 128, 'Типовой вариант', p.get('typevar_code') or p.get('typevar') or '', vx=150)
    row(455, 128, 'Шифр оператора', val('operator_code','00'), vx=150)
    t(275, 190, 'Р Е Г У Л И Р У Е М Ы Е   П А Р А М Е Т Р Ы', 10, True)
    c.create_line(272, 207, 620, 207, fill='#222')
    xL, xR = 42, 430
    y = 245
    for lab,k in [('Частота УЗК, МГц','freq_mhz'),('Скорость УЗК, м/с','sound_speed'),('Толщина, мм','thickness_mm'),('Ампл. зонд.','amplitude_probe'),('Отсечка, %','cutoff_pct'),('Блокировка','blocking')]:
        row(xL,y,lab,val(k),vx=150); y+=18
    y+=18; line_title(xL+8,y,'П Э П',95); y+=24
    for lab,k in [('№ ПЭП','probe_no'),('вкл. ПЭП','probe_enabled'),('Угол ввода, град.','angle_deg'),('Время в ПЭП, мкс','probe_time_us')]:
        row(xL,y,lab,val(k),vx=150); y+=18
    y+=18; line_title(xL+8,y,'Ч у в с т в и т е л ь н о с т ь',210); y+=24
    for lab,k in [('Усиление, дБ','gain_db'),('Треб. чувст., дБ','required_sens_db'),('Факт. чувст., дБ','actual_sens_db'),('Доп. усиление, дБ','extra_gain_db'),('Вкл. доп. усиления','extra_gain_enabled')]:
        row(xL,y,lab,val(k),vx=150); y+=18
    y+=18; line_title(xL+8,y,'Р а з в е р т к а',140); y+=24
    for lab,k in [('Тип','sweep_type'),('Длительность','sweep_duration'),('Задержка','sweep_delay'),('W-развертка','w_sweep_enabled'),('Огибающая','envelope_enabled')]:
        row(xL,y,lab,val(k),vx=150,width=260); y+=18
    y+=18; line_title(xL+8,y,'Л у п а',80); y+=24
    for lab,k in [('Вкл.','magnifier_enabled'),('Вид','magnifier_type')]:
        row(xL,y,lab,val(k),vx=150); y+=18
    y = 245
    line_title(xR,y-22,'Н а с т р о й к а   п о   С О',240)
    for lab,k in [('Нач. зоны ВС','so_start'),('Конец зоны ВС','so_end')]: row(xR,y,lab,val(k),vx=140,width=245); y+=18
    y+=18; line_title(xR,y-20,'З о н а   В С 1',150)
    for lab,k in [('Начало','vs1_start'),('Конец','vs1_end'),('Метод','vs1_method'),('Порог, %','vs1_threshold_pct')]: row(xR,y,lab,val(k),vx=140,width=245); y+=18
    y+=18; line_title(xR,y-20,'З о н а   В С 2',150)
    for lab,k in [('Начало','vs2_start'),('Конец','vs2_end'),('Метод','vs2_method'),('Порог, %','vs2_threshold_pct')]: row(xR,y,lab,val(k),vx=140,width=245); y+=18
    y+=18; line_title(xR,y-20,'А Р У',70)
    for lab,k in [('Вкл.','aru_enabled'),('Начало','aru_start'),('Конец','aru_end')]: row(xR,y,lab,val(k),vx=140,width=245); y+=18
    y+=18; line_title(xR,y-20,'В Р Ч',70)
    for lab,k in [('Тип ВРЧ','vrch_type'),('Индикация','vrch_indication'),('Начало','vrch_start'),('Конец','vrch_end'),('Амплитуда, дБ','vrch_amp_db'),('Форма','vrch_shape'),('До ВРЧ, дБ','before_vrch_db'),('После ВРЧ, дБ','after_vrch_db')]: row(xR,y,lab,val(k),vx=140,width=245); y+=18
    t(245, 878, 'Ф И К С И Р О В А Н Н Ы Е   П А Р А М Е Т Р Ы', 9, True)
    c.create_line(242, 894, 625, 894, fill='#222')
    row(42, 918, 'Пер. зондирования', val('probing_period'), vx=150)
    row(42, 938, 'Порог, %', val('fixed_threshold_pct'), vx=150)
    row(430, 918, 'Част. зонд., Гц', val('probing_freq_hz'), vx=140)
    row(430, 938, 'Доп. метка', val('additional_mark'), vx=140, width=250)


def _v22_a4_canvas_from(src: tk.Canvas, owner: tk.Misc, margin: int = 36) -> tk.Canvas:
    try:
        src.update_idletasks()
        cw = int(float(src.cget('width'))); ch = int(float(src.cget('height')))
    except Exception:
        cw, ch = 900, 1200
    # Stronger shrink so printed A4 does not overlap.  Preview zoom is visual only.
    scale = min((V19_A4_W-margin*2)/max(1,cw), (V19_A4_H-margin*2)/max(1,ch), 1.0) * 0.82
    c = tk.Canvas(owner, bg='white', width=V19_A4_W, height=V19_A4_H, highlightthickness=0)
    _v20_clone_canvas_items(src, c, scale, margin, margin)  # type: ignore[name-defined]
    return c


def _v22_print_preview(owner: tk.Misc, canvas: Optional[tk.Canvas] = None, title: str = 'peleng_sheet') -> None:
    try:
        if canvas is None:
            canvas = getattr(owner, 'page_canvas', None)
        if not isinstance(canvas, tk.Canvas):
            canvas = _v19_make_report_print_canvas(owner)  # type: ignore[name-defined]
        if not isinstance(canvas, tk.Canvas):
            messagebox.showerror('Печать', 'Не найден Canvas листа для печати', parent=owner); return
        a4_canvas = canvas if (int(float(canvas.cget('width'))) == V19_A4_W and int(float(canvas.cget('height'))) == V19_A4_H) else _v22_a4_canvas_from(canvas, owner)
        win = tk.Toplevel(owner); win.title('Предпросмотр печати A4'); win.geometry('820x900')
        top = ttk.Frame(win, padding=6); top.pack(fill=tk.X)
        printers = _v17_enum_printers()  # type: ignore[name-defined]
        default_prn = _v17_default_printer()  # type: ignore[name-defined]
        ttk.Label(top, text='Принтер:').pack(side=tk.LEFT, padx=(0,4))
        prn_var = tk.StringVar(value=default_prn or (printers[0] if printers else ''))
        ttk.Combobox(top, textvariable=prn_var, values=printers, width=38, state=('readonly' if printers else 'normal')).pack(side=tk.LEFT, padx=4)
        ttk.Label(top, text='Масштаб:').pack(side=tk.LEFT, padx=(12,4))
        zoom_var = tk.StringVar(value='65%')
        zoom = ttk.Combobox(top, textvariable=zoom_var, values=['35%','45%','55%','65%','70%','80%','90%','100%'], width=6, state='readonly')
        zoom.pack(side=tk.LEFT)
        body = tk.Canvas(win, bg='#555', highlightthickness=0)
        vsb = ttk.Scrollbar(win, orient=tk.VERTICAL, command=body.yview); hsb = ttk.Scrollbar(win, orient=tk.HORIZONTAL, command=body.xview)
        body.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set); body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); vsb.pack(side=tk.RIGHT, fill=tk.Y); hsb.pack(side=tk.BOTTOM, fill=tk.X)
        def render(*_):
            try: z = float(zoom_var.get().strip().rstrip('%'))/100.0
            except Exception: z = 0.65
            body.delete('all')
            page = tk.Canvas(body, bg='white', width=int(V19_A4_W*z), height=int(V19_A4_H*z), bd=1, relief=tk.SOLID, highlightthickness=0)
            body.create_window(14,14,anchor='nw',window=page); body.configure(scrollregion=(0,0,int(V19_A4_W*z)+28,int(V19_A4_H*z)+28))
            _v20_clone_canvas_items(a4_canvas, page, z)  # type: ignore[name-defined]
        zoom.bind('<<ComboboxSelected>>', render); render()
        safe_title = re.sub(r'[^A-Za-z0-9А-Яа-я_.-]+','_',str(title or 'peleng_sheet'))[:80]
        def do_print():
            prn = prn_var.get().strip()
            if _v22_print_canvas_bitmap(a4_canvas, prn, safe_title):
                messagebox.showinfo('Печать', 'Задание отправлено на принтер', parent=win); return
            messagebox.showwarning('Печать', 'Прямая печать недоступна. Установите зависимости:\npython -m pip install pywin32 pillow\n\nПосле установки повторите печать.', parent=win)
        ttk.Button(top, text='Печать', command=do_print).pack(side=tk.LEFT, padx=8)
        ttk.Button(top, text='Закрыть', command=win.destroy).pack(side=tk.RIGHT, padx=4)
    except Exception as exc:
        messagebox.showerror('Печать', str(exc), parent=owner)

# Apply v22 patches.
try:
    NativeSettingSheet.PAGE_W = 760  # type: ignore[name-defined]
    NativeSettingSheet.PAGE_H = 990  # type: ignore[name-defined]
    SettingDetail.PAGE_W = 760  # type: ignore[name-defined]
    SettingDetail.PAGE_H = 990  # type: ignore[name-defined]
    NativeSettingSheet.__init__ = _v22_setting_init  # type: ignore[name-defined]
    SettingDetail.__init__ = _v22_setting_init  # type: ignore[name-defined]
    NativeSettingSheet._build = _v22_setting_build  # type: ignore[name-defined]
    SettingDetail._build = _v22_setting_build  # type: ignore[name-defined]
    NativeSettingSheet._draw = _v22_setting_draw  # type: ignore[name-defined]
    SettingDetail._draw = _v22_setting_draw  # type: ignore[name-defined]
except Exception:
    pass
try:
    _v19_a4_canvas_from = _v22_a4_canvas_from  # type: ignore[assignment]
    _v20_a4_canvas_from = _v22_a4_canvas_from  # type: ignore[assignment]
    _v17_print_preview = _v22_print_preview  # type: ignore[assignment]
    _v18_print_preview = _v22_print_preview  # type: ignore[assignment]
    _v19_print_preview = _v22_print_preview  # type: ignore[assignment]
    _v20_print_preview = _v22_print_preview  # type: ignore[assignment]
    _v21_print_preview = _v22_print_preview  # type: ignore[assignment]
    _v17_wrap_buttons(NativeReportSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(NativeAscanProtocolSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(SettingDetail)  # type: ignore[name-defined]
except Exception:
    pass



# ---------------------------------------------------------------------------
# v23: readable multi-page A4 print, single persistent decoded DB, settings.ini.
# ---------------------------------------------------------------------------
APP_BUILD_VERSION = "v23 readable A4 + single decoded DB + settings.ini"

# v23 policy requested by operator:
#   * do not create peleng_vagon643_idx.sqlite3;
#   * keep only one persistent user SQLite DB with three decoded tables;
#   * store enterprise/subdivision/operator directory and DB path in settings.ini;
#   * print readable A4, splitting to several pages when necessary.
try:
    import configparser as _v23_configparser
except Exception:  # pragma: no cover
    _v23_configparser = None

def _portable_app_dir() -> str:
    """Directory for portable runtime files next to .py or frozen .exe."""
    try:
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(__file__))


def _portable_candidate_dirs() -> list[str]:
    """Search roots for portable files when cwd/exe/script dirs differ."""
    roots: list[str] = []
    for value in (
        _portable_app_dir(),
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
        getattr(sys, "_MEIPASS", ""),
    ):
        try:
            if value:
                root = os.path.abspath(str(value))
                if root not in roots:
                    roots.append(root)
        except Exception:
            pass
    return roots


def _portable_existing_file(filename: str) -> str:
    """Return an existing portable file from exe/cwd/script search roots."""
    for root in _portable_candidate_dirs():
        candidate = os.path.join(root, filename)
        if os.path.exists(candidate):
            return candidate
    return ""


def _portable_resolve_data_path(path: Any, default_name: str = "peleng_vagon643_decoded.sqlite3") -> str:
    """Resolve INI paths relative to settings.ini and tolerate moved EXE folders."""
    raw = str(path or "").strip()
    if not raw:
        raw = default_name
    raw = os.path.expanduser(raw)
    if os.path.isabs(raw):
        # Portable EXE may be moved with settings.ini that still contains an
        # absolute path from the build/source PC. Prefer the DB beside the EXE.
        found = _portable_existing_file(os.path.basename(raw))
        if found:
            return found
        if os.path.exists(raw):
            return os.path.abspath(raw)
        return os.path.abspath(raw)
    settings_dir = os.path.dirname(os.path.abspath(V23_SETTINGS_INI)) if "V23_SETTINGS_INI" in globals() else _portable_app_dir()
    primary = os.path.abspath(os.path.join(settings_dir, raw))
    if os.path.exists(primary):
        return primary
    found = _portable_existing_file(os.path.basename(raw))
    if found:
        return found
    return primary


V23_SCRIPT_DIR = _portable_app_dir()
V23_SETTINGS_INI = _portable_existing_file("settings.ini") or os.path.join(V23_SCRIPT_DIR, "settings.ini")
V23_DEFAULT_DECODED_DB = _portable_existing_file("peleng_vagon643_decoded.sqlite3") or os.path.join(V23_SCRIPT_DIR, "peleng_vagon643_decoded.sqlite3")

# Legacy default before v25 wiring runs. install_latest_v25_overrides() replaces
# this with peleng_vagon643_basket.sqlite3 for persistent raw/basket storage.
IDX_DB_DEFAULT = ":memory:"


def _v23_ini_defaults() -> dict[str, Any]:
    return {
        "sqlite_path": V23_DEFAULT_DECODED_DB,
        "enterprise": "ВЧДэ Россошь",
        "subdivision": "НК",
        "operators": {},
    }


def _v23_load_ini() -> dict[str, Any]:
    cfg = _v23_ini_defaults()
    if _v23_configparser is None:
        return cfg
    cp = _v23_configparser.ConfigParser()
    try:
        if os.path.exists(V23_SETTINGS_INI):
            cp.read(V23_SETTINGS_INI, encoding="utf-8")
        if cp.has_section("sqlite"):
            path = cp.get("sqlite", "path", fallback=cfg["sqlite_path"]).strip()
            if path:
                cfg["sqlite_path"] = _portable_resolve_data_path(path)
        if cp.has_section("report"):
            cfg["enterprise"] = cp.get("report", "enterprise", fallback=cfg["enterprise"])
            cfg["subdivision"] = cp.get("report", "subdivision", fallback=cfg["subdivision"])
        ops: dict[str, str] = {}
        if cp.has_section("operators"):
            for k, v in cp.items("operators"):
                code = _normalize_operator_code(k) if "_normalize_operator_code" in globals() else str(k).strip()
                if code:
                    ops[code] = str(v).strip()
        cfg["operators"] = ops
    except Exception:
        pass
    return cfg


def _v23_save_ini(cfg: dict[str, Any]) -> None:
    if _v23_configparser is None:
        return
    try:
        os.makedirs(os.path.dirname(os.path.abspath(V23_SETTINGS_INI)), exist_ok=True)
    except Exception:
        pass
    cp = _v23_configparser.ConfigParser()
    cp["sqlite"] = {"path": str(cfg.get("sqlite_path") or V23_DEFAULT_DECODED_DB)}
    cp["report"] = {
        "enterprise": str(cfg.get("enterprise") or ""),
        "subdivision": str(cfg.get("subdivision") or ""),
    }
    ops = cfg.get("operators") or {}
    cp["operators"] = {str(k): str(v) for k, v in dict(ops).items() if str(k).strip()}
    os.makedirs(os.path.dirname(V23_SETTINGS_INI) or ".", exist_ok=True)
    with open(V23_SETTINGS_INI, "w", encoding="utf-8") as f:
        cp.write(f)


# Backward-compatible config API used by existing UI dialogs.
def _fields_load_config() -> dict[str, Any]:  # type: ignore[override]
    cfg = _v23_load_ini()
    return {"enterprise": cfg["enterprise"], "subdivision": cfg["subdivision"], "operators": cfg["operators"]}


def _fields_save_config(cfg: dict[str, Any]) -> None:  # type: ignore[override]
    old = _v23_load_ini()
    old["enterprise"] = str(cfg.get("enterprise") or "").strip()
    old["subdivision"] = str(cfg.get("subdivision") or "").strip()
    old["operators"] = {str(k).strip(): str(v).strip() for k, v in dict(cfg.get("operators") or {}).items() if str(k).strip()}
    _v23_save_ini(old)


def _report_enterprise() -> str:  # type: ignore[override]
    return str(_v23_load_ini().get("enterprise") or "")


def _report_subdivision() -> str:  # type: ignore[override]
    return str(_v23_load_ini().get("subdivision") or "")


def _operator_name_for_code(code: Any, fallback: str = "") -> str:  # type: ignore[override]
    code_s = _normalize_operator_code(code) if "_normalize_operator_code" in globals() else str(code or "").strip()
    ops = _v23_load_ini().get("operators") or {}
    return str(ops.get(code_s) or ops.get(str(code_s).lstrip("0")) or fallback or "").strip()


# Persistent decoded DB path comes from settings.ini.  It is never derived from
# the in-memory runtime DB path and is not deleted/recreated on startup.
def _v20_user_db_path(db: Any = None) -> str:  # type: ignore[override]
    return str(_v23_load_ini().get("sqlite_path") or V23_DEFAULT_DECODED_DB)

_v19_clean_db_path = _v20_user_db_path  # type: ignore[assignment]


def _v23_clean_connect(db: Any = None):
    path = _v20_user_db_path(db)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    # Create only the three decoded tables.  Do not DROP; the DB accumulates.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            control_date TEXT,
            control_time TEXT,
            device_no TEXT,
            software_version TEXT,
            enterprise TEXT,
            subdivision TEXT,
            operator_code TEXT,
            operator_name TEXT,
            setting_no TEXT,
            object_type TEXT,
            object_number TEXT,
            smelting TEXT,
            factory TEXT,
            production_year TEXT,
            side TEXT,
            neck TEXT,
            rim TEXT,
            wheel_turning TEXT,
            crest TEXT,
            defects_count TEXT,
            protocol TEXT
        );
        CREATE TABLE IF NOT EXISTS protocols (
            protocol_no TEXT,
            control_date TEXT,
            control_time TEXT,
            device_no TEXT,
            software_version TEXT,
            enterprise TEXT,
            subdivision TEXT,
            operator_code TEXT,
            operator_name TEXT,
            setting_no TEXT,
            object_type TEXT,
            object_number TEXT,
            smelting TEXT,
            factory TEXT,
            production_year TEXT,
            side TEXT,
            neck TEXT,
            detail TEXT,
            conclusion TEXT,
            defect_m TEXT,
            defect_y TEXT,
            defect_x TEXT,
            defect_r TEXT,
            defect_detectability TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            setting_no TEXT,
            setting_date TEXT,
            setting_time TEXT,
            device_no TEXT,
            software_version TEXT,
            operator_code TEXT,
            object_type TEXT,
            freq_mhz TEXT,
            sound_speed TEXT,
            thickness_mm TEXT,
            amplitude_probe TEXT,
            cutoff_pct TEXT,
            blocking TEXT,
            probe_no TEXT,
            probe_enabled TEXT,
            angle_deg TEXT,
            probe_time_us TEXT,
            gain_db TEXT,
            required_sens_db TEXT,
            actual_sens_db TEXT,
            extra_gain_db TEXT,
            sweep_type TEXT,
            sweep_duration TEXT,
            sweep_delay TEXT,
            w_sweep_enabled TEXT,
            envelope_enabled TEXT,
            so_start TEXT,
            so_end TEXT,
            vs1_start TEXT,
            vs1_end TEXT,
            vs1_method TEXT,
            vs1_threshold_pct TEXT,
            vs2_start TEXT,
            vs2_end TEXT,
            vs2_method TEXT,
            vs2_threshold_pct TEXT,
            aru_enabled TEXT,
            aru_start TEXT,
            aru_end TEXT,
            vrch_type TEXT,
            vrch_indication TEXT,
            vrch_start TEXT,
            vrch_end TEXT,
            vrch_amplitude_db TEXT,
            vrch_shape TEXT,
            before_vrch_db TEXT,
            after_vrch_db TEXT,
            extra_gain_enabled TEXT
        );
    """)
    conn.commit()
    return conn

_v20_clean_connect = _v23_clean_connect  # type: ignore[assignment]
_v19_clean_connect = _v23_clean_connect  # type: ignore[assignment]

# Re-bind the sync helpers so they use the non-dropping v23 connector even if
# older functions close over _v20_clean_connect by name.
def _v23_sync_clean_report(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("reports", int(addr))
        if not row:
            return
        vals = _native_report_detail_values(db, row)  # type: ignore[name-defined]
        operator_code = str(row["KODOPERA"] or "") if "KODOPERA" in row.keys() else ""
        operator_name = _operator_name_for_code(operator_code, str(row["NAMEOPERA"] or "") if "NAMEOPERA" in row.keys() else "")
        tv = row["TYPEVAR"] if "TYPEVAR" in row.keys() else vals.get("obj_type")
        object_type = str(vals.get("obj_type") or _v19_typevar_text(tv))  # type: ignore[name-defined]
        conn = _v23_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT INTO reports(
                    control_date,control_time,device_no,software_version,enterprise,subdivision,
                    operator_code,operator_name,setting_no,object_type,object_number,smelting,
                    factory,production_year,side,neck,rim,wheel_turning,crest,defects_count,protocol
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(vals.get("date") or ""), str(vals.get("time") or ""),
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                _report_enterprise(), _report_subdivision(), operator_code, operator_name,
                str(vals.get("setting_no") or ""), object_type, str(vals.get("numobj") or ""),
                str(vals.get("smelting") or ""), str(vals.get("factory") or ""),
                str(vals.get("year") or ""), str(vals.get("side") or ""), str(vals.get("neck") or ""),
                str(vals.get("rim") or ""), str(vals.get("wheel_turn") or ""), str(vals.get("crest") or ""),
                str(vals.get("defects") or ""), str(row["PROTOCOL"] or "") if "PROTOCOL" in row.keys() else "",
            ))
        conn.close()
    except Exception:
        pass


def _v23_sync_clean_protocol(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("protocols", int(addr))
        rr = db.get_raw_by_addr(int(addr))
        raw = bytes(rr["raw"]) if rr else b""
        if not row:
            return
        vals = _v19_protocol_values(db, row, raw)  # type: ignore[name-defined]
        operator_code = str(row["KODOPERA"] or "") if "KODOPERA" in row.keys() else ""
        conn = _v23_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT INTO protocols(
                    protocol_no,control_date,control_time,device_no,software_version,enterprise,subdivision,
                    operator_code,operator_name,setting_no,object_type,object_number,smelting,factory,
                    production_year,side,neck,detail,conclusion,defect_m,defect_y,defect_x,defect_r,defect_detectability
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(row["NUMKOD"] or "") if "NUMKOD" in row.keys() else str(int(addr)%1000),
                str(row["DATEFORM"] or "") if "DATEFORM" in row.keys() else "",
                str(row["TIMEFORM"] or "") if "TIMEFORM" in row.keys() else "",
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                _report_enterprise(), _report_subdivision(), operator_code,
                _operator_name_for_code(operator_code, str(row["NAMEOPERA"] or "") if "NAMEOPERA" in row.keys() else ""),
                str(row["SETTING_NO"] or "") if "SETTING_NO" in row.keys() else "",
                vals.get("object_type",""), vals.get("object_number",""), vals.get("smelting",""),
                vals.get("factory",""), vals.get("year",""), vals.get("side",""), vals.get("neck",""),
                vals.get("detail",""), "Признак дефекта отсутствует", vals.get("defect_m",""),
                vals.get("defect_y",""), vals.get("defect_x",""), vals.get("defect_r",""), vals.get("defect_detectability",""),
            ))
        conn.close()
    except Exception:
        pass


def _v23_sync_clean_setting(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("settings", int(addr))
        rr = db.get_raw_by_addr(int(addr))
        raw = bytes(rr["raw"]) if rr else b""
        if not row:
            return
        p = decode_nastr2_params_643(raw, int(addr)) if raw else {}  # type: ignore[name-defined]
        tv = p.get("typevar_code") or (row["TYPEVAR"] if "TYPEVAR" in row.keys() else "")
        conn = _v23_clean_connect(db)
        with conn:
            conn.execute("""
                INSERT INTO settings(
                    setting_no,setting_date,setting_time,device_no,software_version,operator_code,object_type,
                    freq_mhz,sound_speed,thickness_mm,amplitude_probe,cutoff_pct,blocking,probe_no,probe_enabled,
                    angle_deg,probe_time_us,gain_db,required_sens_db,actual_sens_db,extra_gain_db,sweep_type,
                    sweep_duration,sweep_delay,w_sweep_enabled,envelope_enabled,so_start,so_end,vs1_start,vs1_end,
                    vs1_method,vs1_threshold_pct,vs2_start,vs2_end,vs2_method,vs2_threshold_pct,aru_enabled,
                    aru_start,aru_end,vrch_type,vrch_indication,vrch_start,vrch_end,vrch_amplitude_db,vrch_shape,
                    before_vrch_db,after_vrch_db,extra_gain_enabled
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(p.get("setting_no") or (int(addr)-1000 if 1000 <= int(addr) <= 1999 else int(addr))),
                str(p.get("date") or (row["DATEFORM"] if "DATEFORM" in row.keys() else "")),
                str(p.get("time") or (row["TIMEFORM"] if "TIMEFORM" in row.keys() else "")),
                str(row["NUMPRIB"] or "") if "NUMPRIB" in row.keys() else "",
                str(row["NUMVERS"] or "") if "NUMVERS" in row.keys() else "",
                str(p.get("operator_code") or (row["KODOPERA"] if "KODOPERA" in row.keys() else "")),
                _v19_typevar_text(tv),  # type: ignore[name-defined]
                str(p.get("freq_mhz") or ""), str(p.get("sound_speed") or ""), str(p.get("thickness_mm") or ""),
                str(p.get("amplitude_probe") or ""), str(p.get("cutoff_pct") or ""), str(p.get("blocking") or ""),
                str(p.get("probe_no") or ""), str(p.get("probe_enabled") or ""), str(p.get("angle_deg") or ""),
                str(p.get("probe_time_us") or ""), str(p.get("gain_db") or ""), str(p.get("required_sens_db") or ""),
                str(p.get("actual_sens_db") or ""), str(p.get("extra_gain_db") or ""), str(p.get("sweep_type") or ""),
                str(p.get("sweep_duration") or ""), str(p.get("sweep_delay") or ""), str(p.get("w_sweep_enabled") or ""),
                str(p.get("envelope_enabled") or ""), str(p.get("so_start") or ""), str(p.get("so_end") or ""),
                str(p.get("vs1_start") or ""), str(p.get("vs1_end") or ""), str(p.get("vs1_method") or ""),
                str(p.get("vs1_threshold_pct") or ""), str(p.get("vs2_start") or ""), str(p.get("vs2_end") or ""),
                str(p.get("vs2_method") or ""), str(p.get("vs2_threshold_pct") or ""), str(p.get("aru_enabled") or ""),
                str(p.get("aru_start") or ""), str(p.get("aru_end") or ""), str(p.get("vrch_type") or p.get("vrch_enabled") or ""),
                str(p.get("vrch_indication") or ""), str(p.get("vrch_start") or ""), str(p.get("vrch_end") or ""),
                str(p.get("vrch_amp_db") or p.get("vrch_amplitude_db") or p.get("vrch_amplitude") or ""),
                str(p.get("vrch_shape") or ""), str(p.get("before_vrch_db") or ""), str(p.get("after_vrch_db") or ""),
                str(p.get("extra_gain_enabled") or ""),
            ))
        conn.close()
    except Exception:
        pass

_v19_sync_clean_report = _v23_sync_clean_report  # type: ignore[assignment]
_v19_sync_clean_protocol = _v23_sync_clean_protocol  # type: ignore[assignment]
_v19_sync_clean_setting = _v23_sync_clean_setting  # type: ignore[assignment]

# settings.ini editor also allows selecting the decoded SQLite file.
try:
    _v23_old_report_settings_build = ReportFieldsSettingsDialog._build  # type: ignore[name-defined]
    def _v23_report_settings_build(self):
        _v23_old_report_settings_build(self)
        try:
            cfg = _v23_load_ini()
            self.sqlite_path_var = tk.StringVar(value=str(cfg.get("sqlite_path") or V23_DEFAULT_DECODED_DB))
            frm = ttk.LabelFrame(self, text="SQLite база дешифровок", padding=6)
            frm.pack(fill=tk.X, padx=10, pady=(0, 8))
            ttk.Entry(frm, textvariable=self.sqlite_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
            def choose():
                path = filedialog.asksaveasfilename(parent=self, title="Файл SQLite", defaultextension=".sqlite3", initialfile=os.path.basename(self.sqlite_path_var.get() or V23_DEFAULT_DECODED_DB), filetypes=[("SQLite", "*.sqlite3"), ("Все файлы", "*.*")])
                if path:
                    self.sqlite_path_var.set(path)
            ttk.Button(frm, text="...", width=4, command=choose).pack(side=tk.LEFT, padx=4)
        except Exception:
            pass
    def _v23_report_settings_save(self):
        self.cfg["enterprise"] = str(self.enterprise_var.get() or "").strip()
        self.cfg["subdivision"] = str(self.subdivision_var.get() or "").strip()
        ini = _v23_load_ini()
        ini["enterprise"] = self.cfg["enterprise"]
        ini["subdivision"] = self.cfg["subdivision"]
        ini["operators"] = self.cfg.get("operators") or {}
        try:
            path = str(getattr(self, "sqlite_path_var", tk.StringVar(value="")).get() or "").strip()
            if path:
                ini["sqlite_path"] = os.path.abspath(os.path.expanduser(path))
        except Exception:
            pass
        _v23_save_ini(ini)
        if self.db is not None:
            _apply_operator_directory_to_sqlite(self.db)
        if self.on_saved:
            try: self.on_saved()
            except Exception: pass
        messagebox.showinfo("Настройки", "Сохранено в settings.ini", parent=self)
        self.destroy()
    ReportFieldsSettingsDialog._build = _v23_report_settings_build  # type: ignore[name-defined]
    ReportFieldsSettingsDialog._save = _v23_report_settings_save  # type: ignore[name-defined]
except Exception:
    pass

# Compact setting sheet that actually fits the visible window: smaller page,
# narrower columns, wrapped long values.  It keeps the native two-column look.
try:
    NativeSettingSheet.PAGE_W = 700  # type: ignore[name-defined]
    NativeSettingSheet.PAGE_H = 900  # type: ignore[name-defined]
    SettingDetail.PAGE_W = 700  # type: ignore[name-defined]
    SettingDetail.PAGE_H = 900  # type: ignore[name-defined]
except Exception:
    pass


def _v23_setting_init(self: Any, master: tk.Misc, row: sqlite3.Row, raw: bytes):
    tk.Toplevel.__init__(self, master)
    self.master_app = master
    self.row = row
    self.raw = bytes(raw or b'')
    try: self.addr = int(row['address'])
    except Exception: self.addr = 0
    try: self.params = decode_nastr2_params_643(self.raw, self.addr)
    except Exception as exc: self.params = {'error': str(exc)}
    self.title('Настройка')
    self.geometry('780x680')
    self.minsize(680, 520)
    self._build()


def _v23_setting_draw(self: Any, c: tk.Canvas) -> None:
    c.delete('all')
    p = getattr(self, 'params', {}) or {}
    def clean(v, default='-'):
        try: return _v15_clean(v, default)  # type: ignore[name-defined]
        except Exception: return str(v if v not in (None, '') else default)
    def val(k, default='-'):
        return clean(p.get(k), default)
    def t(x,y,text,size=6,bold=False,width=None,anchor='nw'):
        c.create_text(x,y,text=str(text or ''),anchor=anchor,fill='#111',font=('Arial',size,'bold' if bold else 'normal'),width=width)
    def row(x,y,label,value,vx=118,width=180):
        t(x,y,label,6); t(x+vx,y,clean(value),6,False,width=width)
    def title(x,y,text,w=130):
        t(x,y,text,7,True); c.create_line(x,y+12,x+w,y+12,fill='#222')
    try: dev, ver = self._header_device_version()
    except Exception: dev = ver = ''
    num = p.get('setting_no') or (getattr(self,'addr',0)-1000 if 1000 <= getattr(self,'addr',0) <= 1999 else getattr(self,'addr',0))
    t(30,26,f'П А Р А М Е Т Р Ы   Н А С Т Р О Й К И   №{num}',10,True)
    t(30,48,f"дефектоскоп УД2-102 № {dev}, {val('date','')} {val('time','')}, Версия {ver}",7)
    row(38,105,'Типовой вариант',p.get('typevar_code') or p.get('typevar') or '',vx=135)
    row(410,105,'Шифр оператора',val('operator_code','00'),vx=128)
    t(260,160,'Р Е Г У Л И Р У Е М Ы Е   П А Р А М Е Т Р Ы',9,True); c.create_line(258,176,555,176,fill='#222')
    xL,xR=38,385
    y=210
    for lab,k in [('Частота УЗК, МГц','freq_mhz'),('Скорость УЗК, м/с','sound_speed'),('Толщина, мм','thickness_mm'),('Ампл. зонд.','amplitude_probe'),('Отсечка, %','cutoff_pct'),('Блокировка','blocking')]: row(xL,y,lab,val(k)); y+=15
    y+=12; title(xL+6,y,'П Э П',80); y+=20
    for lab,k in [('№ ПЭП','probe_no'),('вкл. ПЭП','probe_enabled'),('Угол ввода, град.','angle_deg'),('Время в ПЭП, мкс','probe_time_us')]: row(xL,y,lab,val(k)); y+=15
    y+=12; title(xL+6,y,'Ч у в с т в и т е л ь н о с т ь',180); y+=20
    for lab,k in [('Усиление, дБ','gain_db'),('Треб. чувст., дБ','required_sens_db'),('Факт. чувст., дБ','actual_sens_db'),('Доп. усиление, дБ','extra_gain_db'),('Вкл. доп. усиления','extra_gain_enabled')]: row(xL,y,lab,val(k)); y+=15
    y+=12; title(xL+6,y,'Р а з в е р т к а',120); y+=20
    for lab,k in [('Тип','sweep_type'),('Длительность','sweep_duration'),('Задержка','sweep_delay'),('W-развертка','w_sweep_enabled'),('Огибающая','envelope_enabled')]: row(xL,y,lab,val(k),width=210); y+=15
    y+=12; title(xL+6,y,'Л у п а',70); y+=20
    for lab,k in [('Вкл.','magnifier_enabled'),('Вид','magnifier_type')]: row(xL,y,lab,val(k)); y+=15
    y=210
    title(xR,y-18,'Н а с т р о й к а   п о   С О',210)
    for lab,k in [('Нач. зоны ВС','so_start'),('Конец зоны ВС','so_end')]: row(xR,y,lab,val(k),vx=120,width=190); y+=15
    y+=12; title(xR,y-18,'З о н а   В С 1',130)
    for lab,k in [('Начало','vs1_start'),('Конец','vs1_end'),('Метод','vs1_method'),('Порог, %','vs1_threshold_pct')]: row(xR,y,lab,val(k),vx=120,width=190); y+=15
    y+=12; title(xR,y-18,'З о н а   В С 2',130)
    for lab,k in [('Начало','vs2_start'),('Конец','vs2_end'),('Метод','vs2_method'),('Порог, %','vs2_threshold_pct')]: row(xR,y,lab,val(k),vx=120,width=190); y+=15
    y+=12; title(xR,y-18,'А Р У',60)
    for lab,k in [('Вкл.','aru_enabled'),('Начало','aru_start'),('Конец','aru_end')]: row(xR,y,lab,val(k),vx=120,width=190); y+=15
    y+=12; title(xR,y-18,'В Р Ч',60)
    for lab,k in [('Тип ВРЧ','vrch_type'),('Индикация','vrch_indication'),('Начало','vrch_start'),('Конец','vrch_end'),('Амплитуда, дБ','vrch_amp_db'),('Форма','vrch_shape'),('До ВРЧ, дБ','before_vrch_db'),('После ВРЧ, дБ','after_vrch_db')]: row(xR,y,lab,val(k),vx=120,width=190); y+=15
    t(230,782,'Ф И К С И Р О В А Н Н Ы Е   П А Р А М Е Т Р Ы',8,True); c.create_line(228,796,555,796,fill='#222')
    row(38,818,'Пер. зондирования',val('probing_period'),vx=135)
    row(38,836,'Порог, %',val('fixed_threshold_pct'),vx=135)
    row(385,818,'Част. зонд., Гц',val('probing_freq_hz'),vx=120)
    row(385,836,'Доп. метка',val('additional_mark'),vx=120,width=190)

try:
    SettingDetail.__init__ = _v23_setting_init  # type: ignore[name-defined]
    NativeSettingSheet.__init__ = _v23_setting_init  # type: ignore[name-defined]
    SettingDetail._draw = _v23_setting_draw  # type: ignore[name-defined]
    NativeSettingSheet._draw = _v23_setting_draw  # type: ignore[name-defined]
except Exception:
    pass

# ---------------------------------------------------------------------------
# Multi-page readable A4 printing.  Instead of shrinking a long/wide sheet onto
# one page, split vertically into pages at a readable scale.  Orientation and
# scale are selectable in preview.
# ---------------------------------------------------------------------------
V23_A4_PORTRAIT = (794, 1123)
V23_A4_LANDSCAPE = (1123, 794)


def _v23_item_bbox(src: tk.Canvas, item: int):
    try:
        b = src.bbox(item)
        if b: return tuple(float(x) for x in b)
    except Exception:
        pass
    try:
        coords = src.coords(item)
        if coords:
            xs = coords[0::2]; ys = coords[1::2]
            return (min(xs), min(ys), max(xs), max(ys))
    except Exception:
        pass
    return (0.0, 0.0, 0.0, 0.0)


def _v23_scaled_font_from_canvas(src: tk.Canvas, item: int, scale: float):
    try:
        import tkinter.font as tkfont
        f = tkfont.Font(font=src.itemcget(item, 'font'))
        fam = f.actual('family') or 'Arial'
        size = abs(int(f.actual('size') or 8))
        weight = f.actual('weight') or 'normal'
        slant = f.actual('slant') or 'roman'
        return (fam, max(5, int(round(size*scale))), weight, slant)
    except Exception:
        return ('Arial', max(5, int(round(8*scale))))


def _v23_clone_slice(src: tk.Canvas, dst: tk.Canvas, scale: float, margin: int, y_start: float, y_end: float):
    try: src.update_idletasks()
    except Exception: pass
    for item in src.find_all():
        typ = src.type(item)
        bx1,by1,bx2,by2 = _v23_item_bbox(src,item)
        if by2 < y_start-8 or by1 > y_end+8:
            continue
        coords = src.coords(item)
        if not coords:
            continue
        sc = []
        for i,v in enumerate(coords):
            if i % 2 == 0: sc.append(margin + float(v)*scale)
            else: sc.append(margin + (float(v)-y_start)*scale)
        try:
            if typ == 'line':
                dst.create_line(*sc, fill=src.itemcget(item,'fill') or '#000', width=max(1,float(src.itemcget(item,'width') or 1)*scale), dash=src.itemcget(item,'dash') or None)
            elif typ == 'rectangle':
                dst.create_rectangle(*sc, outline=src.itemcget(item,'outline') or '#000', fill=src.itemcget(item,'fill') or '', width=max(1,float(src.itemcget(item,'width') or 1)*scale))
            elif typ == 'oval':
                dst.create_oval(*sc, outline=src.itemcget(item,'outline') or '#000', fill=src.itemcget(item,'fill') or '', width=max(1,float(src.itemcget(item,'width') or 1)*scale))
            elif typ == 'polygon':
                dst.create_polygon(*sc, outline=src.itemcget(item,'outline') or '#000', fill=src.itemcget(item,'fill') or '')
            elif typ == 'text':
                width = src.itemcget(item,'width')
                try: width = float(width)*scale if width else 0
                except Exception: width = 0
                dst.create_text(sc[0], sc[1], text=src.itemcget(item,'text'), anchor=src.itemcget(item,'anchor') or 'nw', fill=src.itemcget(item,'fill') or '#000', font=_v23_scaled_font_from_canvas(src,item,scale), width=width)
            elif typ == 'window':
                # nested graph canvas: render its visible slice as a bitmap-like
                # clone by copying its items into the destination at the window origin.
                wname = src.itemcget(item,'window')
                if wname:
                    try:
                        child = src.nametowidget(wname)
                        if isinstance(child, tk.Canvas):
                            tmp = tk.Canvas(dst, bg=child.cget('bg') or 'white', width=int(float(child.cget('width'))*scale), height=int(float(child.cget('height'))*scale), highlightthickness=0)
                            _v23_clone_slice(child, tmp, scale, 0, 0, float(child.cget('height')))
                            dst.create_window(sc[0], sc[1], anchor='nw', window=tmp)
                    except Exception:
                        pass
        except Exception:
            continue


def _v23_make_pages(src: tk.Canvas, owner: tk.Misc, orientation: str = 'portrait', scale_pct: int = 100, margin: int = 34) -> list[tk.Canvas]:
    try:
        src.update_idletasks(); cw = float(src.cget('width')); ch = float(src.cget('height'))
    except Exception:
        cw, ch = 800.0, 1200.0
    page_w, page_h = V23_A4_LANDSCAPE if orientation == 'landscape' else V23_A4_PORTRAIT
    usable_w = page_w - margin*2
    usable_h = page_h - margin*2
    base_scale = min(float(scale_pct)/100.0, usable_w/max(1.0,cw))
    # Do not shrink below fit width; for readability prefer landscape / pages.
    scale = max(0.40, base_scale)
    slice_h = usable_h / max(0.01, scale)
    n_pages = max(1, int((ch + slice_h - 1)//slice_h))
    pages: list[tk.Canvas] = []
    for i in range(n_pages):
        y0 = i*slice_h
        y1 = min(ch, (i+1)*slice_h)
        page = tk.Canvas(owner, bg='white', width=page_w, height=page_h, highlightthickness=0)
        _v23_clone_slice(src, page, scale, margin, y0, y1)
        if n_pages > 1:
            page.create_text(page_w-margin, page_h-18, text=f'{i+1}/{n_pages}', anchor='se', font=('Arial', 8), fill='#444')
        pages.append(page)
    return pages


def _v23_canvas_to_image(src: tk.Canvas, scale: float = 2.0):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None
    w = int(float(src.cget('width'))*scale); h = int(float(src.cget('height'))*scale)
    img = Image.new('RGB',(max(1,w),max(1,h)),'white')
    draw = ImageDraw.Draw(img)
    def font_for(item, fallback=8):
        try:
            import tkinter.font as tkfont
            f = tkfont.Font(font=src.itemcget(item,'font'))
            size = max(6,int(abs(int(f.actual('size') or fallback))*scale))
            try: return ImageFont.truetype('arial.ttf', size)
            except Exception: return ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()
    for item in src.find_all():
        typ=src.type(item); coords=[float(x)*scale for x in src.coords(item)]
        try:
            if typ=='line' and len(coords)>=4:
                draw.line(coords, fill=src.itemcget(item,'fill') or 'black', width=max(1,int(float(src.itemcget(item,'width') or 1)*scale)))
            elif typ=='rectangle' and len(coords)>=4:
                fill=src.itemcget(item,'fill') or None; outline=src.itemcget(item,'outline') or 'black'
                draw.rectangle(coords[:4], outline=outline, fill=fill, width=max(1,int(float(src.itemcget(item,'width') or 1)*scale)))
            elif typ=='text' and len(coords)>=2:
                draw.text((coords[0],coords[1]), src.itemcget(item,'text') or '', fill=src.itemcget(item,'fill') or 'black', font=font_for(item))
            elif typ=='oval' and len(coords)>=4:
                draw.ellipse(coords[:4], outline=src.itemcget(item,'outline') or 'black', fill=src.itemcget(item,'fill') or None, width=max(1,int(float(src.itemcget(item,'width') or 1)*scale)))
        except Exception:
            pass
    return img


def _v23_print_pages_bitmap(pages: list[tk.Canvas], printer: str, title: str='Peleng') -> bool:
    if os.name != 'nt' or not pages:
        return False
    try:
        from PIL import ImageWin
        import win32ui, win32con  # type: ignore
    except Exception:
        return False
    dc = None
    try:
        dc = win32ui.CreateDC(); dc.CreatePrinterDC(printer or None)
        printable_w = dc.GetDeviceCaps(win32con.HORZRES); printable_h = dc.GetDeviceCaps(win32con.VERTRES)
        dc.StartDoc(str(title or 'Peleng'))
        for page in pages:
            img = _v23_canvas_to_image(page, scale=2.0)
            if img is None: continue
            iw, ih = img.size
            fit = min(printable_w/iw, printable_h/ih)*0.98
            out_w, out_h = int(iw*fit), int(ih*fit)
            ox, oy = int((printable_w-out_w)/2), int((printable_h-out_h)/2)
            dc.StartPage()
            ImageWin.Dib(img).draw(dc.GetHandleOutput(), (ox,oy,ox+out_w,oy+out_h))
            dc.EndPage()
        dc.EndDoc(); dc.DeleteDC(); return True
    except Exception:
        try:
            if dc: dc.AbortDoc(); dc.DeleteDC()
        except Exception: pass
        return False


def _v23_print_preview(owner: tk.Misc, canvas: Optional[tk.Canvas]=None, title: str='peleng_sheet') -> None:
    try:
        if canvas is None: canvas = getattr(owner,'page_canvas',None)
        if not isinstance(canvas, tk.Canvas):
            try: canvas = _v19_make_report_print_canvas(owner)  # type: ignore[name-defined]
            except Exception: canvas = None
        if not isinstance(canvas, tk.Canvas):
            messagebox.showerror('Печать','Не найден Canvas листа для печати',parent=owner); return
        win = tk.Toplevel(owner); win.title('Предпросмотр печати A4'); win.geometry('980x820')
        top = ttk.Frame(win,padding=6); top.pack(fill=tk.X)
        printers = _v17_enum_printers() if '_v17_enum_printers' in globals() else []  # type: ignore[name-defined]
        default_prn = _v17_default_printer() if '_v17_default_printer' in globals() else ''  # type: ignore[name-defined]
        ttk.Label(top,text='Принтер:').pack(side=tk.LEFT,padx=(0,4))
        prn_var=tk.StringVar(value=default_prn or (printers[0] if printers else ''))
        ttk.Combobox(top,textvariable=prn_var,values=printers,width=34,state=('readonly' if printers else 'normal')).pack(side=tk.LEFT,padx=4)
        ttk.Label(top,text='Ориентация:').pack(side=tk.LEFT,padx=(10,4))
        orient_var=tk.StringVar(value='Альбомная' if isinstance(owner, NativeReportSheet) else 'Книжная')
        ttk.Combobox(top,textvariable=orient_var,values=['Книжная','Альбомная'],width=10,state='readonly').pack(side=tk.LEFT)
        ttk.Label(top,text='Масштаб печати:').pack(side=tk.LEFT,padx=(10,4))
        scale_var=tk.StringVar(value='100%')
        ttk.Combobox(top,textvariable=scale_var,values=['70%','80%','90%','100%','110%','120%','130%','140%'],width=7,state='readonly').pack(side=tk.LEFT)
        page_label=tk.StringVar(value='')
        body=tk.Canvas(win,bg='#555',highlightthickness=0); body.pack(fill=tk.BOTH,expand=True,side=tk.LEFT)
        vsb=ttk.Scrollbar(win,orient=tk.VERTICAL,command=body.yview); vsb.pack(side=tk.RIGHT,fill=tk.Y); body.configure(yscrollcommand=vsb.set)
        state={'pages':[], 'idx':0}
        def rebuild(*_):
            try: pct=int(scale_var.get().rstrip('%'))
            except Exception: pct=100
            orient='landscape' if orient_var.get().startswith('А') else 'portrait'
            state['pages']=_v23_make_pages(canvas, body, orient, pct)
            state['idx']=min(state['idx'], max(0,len(state['pages'])-1))
            show()
        def show():
            body.delete('all')
            pages=state['pages']
            if not pages: return
            pg=pages[state['idx']]
            z=0.72
            view=tk.Canvas(body,bg='white',width=int(float(pg.cget('width'))*z),height=int(float(pg.cget('height'))*z),bd=1,relief=tk.SOLID,highlightthickness=0)
            body.create_window(18,18,anchor='nw',window=view); body.configure(scrollregion=(0,0,int(float(pg.cget('width'))*z)+40,int(float(pg.cget('height'))*z)+40))
            _v23_clone_slice(pg, view, z, 0, 0, float(pg.cget('height')))
            page_label.set(f"Стр. {state['idx']+1}/{len(pages)}")
        def prev(): state.__setitem__('idx',max(0,state['idx']-1)); show()
        def nextp(): state.__setitem__('idx',min(len(state['pages'])-1,state['idx']+1)); show()
        def do_print():
            if not _v23_print_pages_bitmap(state.get('pages') or [], prn_var.get().strip(), title):
                messagebox.showwarning('Печать','Прямая печать недоступна. Установите:\npython -m pip install pywin32 pillow',parent=win)
            else:
                messagebox.showinfo('Печать','Задание отправлено на принтер',parent=win)
        ttk.Button(top,text='◀',command=prev,width=3).pack(side=tk.LEFT,padx=(10,2))
        ttk.Label(top,textvariable=page_label,width=10).pack(side=tk.LEFT)
        ttk.Button(top,text='▶',command=nextp,width=3).pack(side=tk.LEFT,padx=2)
        ttk.Button(top,text='Печать',command=do_print).pack(side=tk.LEFT,padx=10)
        ttk.Button(top,text='Закрыть',command=win.destroy).pack(side=tk.RIGHT)
        for cb in top.winfo_children():
            if isinstance(cb, ttk.Combobox): cb.bind('<<ComboboxSelected>>', rebuild)
        rebuild()
    except Exception as exc:
        messagebox.showerror('Печать',str(exc),parent=owner)

# Apply preview override to all sheet buttons.
try:
    _v17_print_preview = _v23_print_preview  # type: ignore[assignment]
    _v18_print_preview = _v23_print_preview  # type: ignore[assignment]
    _v19_print_preview = _v23_print_preview  # type: ignore[assignment]
    _v20_print_preview = _v23_print_preview  # type: ignore[assignment]
    _v21_print_preview = _v23_print_preview  # type: ignore[assignment]
    _v22_print_preview = _v23_print_preview  # type: ignore[assignment]
    _v17_wrap_buttons(NativeReportSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(NativeAscanProtocolSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(SettingDetail)  # type: ignore[name-defined]
except Exception:
    pass



# ---------------------------------------------------------------------------
# v25: print WYSIWYG controls, encrypted PG settings in settings.ini,
#      report main-grid object number fix, persistent decoded DB clarification.
# ---------------------------------------------------------------------------
APP_BUILD_VERSION = "v25 WYSIWYG print + encrypted ini + report object fix"

# v25 stores PostgreSQL connection settings in settings.ini.  The user/password
# fields are not stored as plaintext.  This is local reversible protection for
# configuration files, not a replacement for OS account security.
def _v25_crypto_keys() -> list[bytes]:
    import hashlib, getpass, platform
    keys: list[bytes] = []
    # Stable portable key: settings.ini must remain readable after PyInstaller
    # rebuilds, double-click EXE launches and folder moves (including Cyrillic
    # paths). This is reversible local obfuscation, not strong encryption.
    stable_seed = "peleng-v25-postgres-settings-enc1"
    keys.append(hashlib.sha256(stable_seed.encode('utf-8')).digest())
    # Backward-compatible key used by earlier builds. It depended on the user,
    # host and app path, which is why EXE restarts/moves could lose credentials.
    try:
        legacy_seed = "|".join([
            getpass.getuser(),
            platform.node(),
            os.path.abspath(V23_SCRIPT_DIR if 'V23_SCRIPT_DIR' in globals() else os.path.dirname(os.path.abspath(__file__))),
            "peleng-v25-postgres",
        ])
        legacy = hashlib.sha256(legacy_seed.encode('utf-8', errors='ignore')).digest()
        if legacy not in keys:
            keys.append(legacy)
    except Exception:
        pass
    return keys


def _v25_crypto_key() -> bytes:
    return _v25_crypto_keys()[0]


def _v25_xor_crypt(data: bytes, key: bytes | None = None) -> bytes:
    k = key or _v25_crypto_key()
    return bytes(b ^ k[i % len(k)] for i, b in enumerate(data))


def _v25_encrypt_text(value: Any) -> str:
    import base64
    s = str(value or "")
    if not s:
        return ""
    return "enc1:" + base64.urlsafe_b64encode(_v25_xor_crypt(s.encode('utf-8'), _v25_crypto_key())).decode('ascii')


def _v25_decrypt_text(value: Any) -> str:
    import base64
    s = str(value or "")
    if not s:
        return ""
    if not s.startswith("enc1:"):
        # Legacy plaintext fallback; will be rewritten encrypted on save.
        return s
    try:
        blob = base64.urlsafe_b64decode(s[5:].encode('ascii'))
    except Exception:
        return ""
    for key in _v25_crypto_keys():
        try:
            text = _v25_xor_crypt(blob, key).decode('utf-8')
            if all((ch >= ' ' or ch in '\t\r\n') for ch in text):
                return text
        except Exception:
            continue
    return ""


def _v25_load_ini_full():
    cp = _v23_configparser.ConfigParser() if '_v23_configparser' in globals() and _v23_configparser is not None else None
    if cp is None:
        return None
    try:
        if os.path.exists(V23_SETTINGS_INI):
            cp.read(V23_SETTINGS_INI, encoding='utf-8')
    except Exception:
        pass
    return cp


def _pg_load_config() -> dict[str, Any]:  # type: ignore[override]
    cfg = _pg_default_config()
    # 1) settings.ini is the canonical source in v25.
    cp = _v25_load_ini_full()
    try:
        if cp is not None and cp.has_section('postgresql'):
            sec = cp['postgresql']
            cfg['host'] = sec.get('host', cfg['host'])
            cfg['port'] = int(sec.get('port', cfg['port']) or 5432)
            cfg['dbname'] = sec.get('dbname', cfg['dbname'])
            cfg['schema'] = sec.get('schema', cfg['schema'])
            cfg['sslmode'] = sec.get('sslmode', cfg['sslmode'])
            cfg['user'] = _v25_decrypt_text(sec.get('user_enc', sec.get('user', cfg['user'])))
            cfg['password'] = _v25_decrypt_text(sec.get('password_enc', sec.get('password', cfg['password'])))
            return cfg
    except Exception:
        pass
    # 2) legacy JSON fallback for migration.
    try:
        if os.path.exists(PG_CONFIG_PATH):
            with open(PG_CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in cfg})
    except Exception:
        pass
    try:
        cfg['port'] = int(cfg.get('port') or 5432)
    except Exception:
        cfg['port'] = 5432
    return cfg


def _pg_save_config(cfg: dict[str, Any]) -> None:  # type: ignore[override]
    clean = _pg_default_config(); clean.update({k: cfg.get(k, clean[k]) for k in clean})
    try: clean['port'] = int(clean.get('port') or 5432)
    except Exception: clean['port'] = 5432
    cp = _v25_load_ini_full()
    if cp is None:
        # Emergency fallback; still avoid plaintext password.
        data = dict(clean)
        data['user_enc'] = _v25_encrypt_text(data.pop('user', ''))
        data['password_enc'] = _v25_encrypt_text(data.pop('password', ''))
        with open(PG_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return
    if not cp.has_section('postgresql'):
        cp.add_section('postgresql')
    cp['postgresql']['host'] = str(clean.get('host') or '127.0.0.1')
    cp['postgresql']['port'] = str(clean.get('port') or 5432)
    cp['postgresql']['dbname'] = str(clean.get('dbname') or 'peleng')
    cp['postgresql']['schema'] = str(clean.get('schema') or 'public')
    cp['postgresql']['sslmode'] = str(clean.get('sslmode') or 'prefer')
    cp['postgresql']['user_enc'] = _v25_encrypt_text(clean.get('user') or '')
    cp['postgresql']['password_enc'] = _v25_encrypt_text(clean.get('password') or '')
    # Remove possible legacy plaintext fields.
    for legacy in ('user', 'password'):
        try: cp.remove_option('postgresql', legacy)
        except Exception: pass
    os.makedirs(os.path.dirname(V23_SETTINGS_INI) or '.', exist_ok=True)
    with open(V23_SETTINGS_INI, 'w', encoding='utf-8') as f:
        cp.write(f)

# Patch the PostgreSQL dialog save message so the user sees settings.ini.
try:
    _old_pg_dialog_save_v25 = PostgresSettingsDialog.save
    def _v25_pg_dialog_save(self):
        try:
            cfg = self._collect()
            _pg_ident(str(cfg.get('schema') or 'public'))
            _pg_save_config(cfg)
            messagebox.showinfo('PostgreSQL', f'Настройки сохранены в settings.ini\nЛогин и пароль записаны в зашифрованном виде.', parent=self)
            self.destroy()
        except Exception as exc:
            messagebox.showerror('PostgreSQL', str(exc), parent=self)
    PostgresSettingsDialog.save = _v25_pg_dialog_save  # type: ignore[name-defined]
except Exception:
    pass

# Fix main report grid object number: use the same detail-sheet decoder that is
# already correct in the double-click report, instead of the stale reports.NUMOBJ.
def _v25_clean_object_number_for_main(db: Any, r: sqlite3.Row, addr: int) -> str:
    try:
        vals = _native_report_detail_values(db, r)  # type: ignore[name-defined]
        num = str(vals.get('numobj') or '').strip()
        if num:
            return num
    except Exception:
        pass
    s = str(r['NUMOBJ'] or '') if r is not None and 'NUMOBJ' in r.keys() else ''
    # Some old decoder variants stored one extra trailing zero in the main grid.
    # Prefer the native detail value; as a fallback trim exactly one suspicious
    # trailing zero from long numeric object numbers.
    if s.isdigit() and len(s) >= 7 and s.endswith('0'):
        return s[:-1]
    return s

try:
    _old_report_display_values_v25 = NativeLikeBasketExactApp._report_display_values  # type: ignore[name-defined]
    def _v25_report_display_values(self, idx_row: sqlite3.Row) -> list[str]:
        addr = int(idx_row['address'])
        r = self.db.row_by_addr('reports', addr)
        if not r:
            return [native_visible_num_for_addr(addr), '', '', '', '', '', '', '', '', '']
        return [
            _native_num_from_report_row(r, addr),
            str(r['DATEFORM'] or ''),
            str(r['TIMEFORM'] or ''),
            _operator_name_for_code(r['KODOPERA'], r['NAMEOPERA']) or str(r['KODOPERA'] or ''),
            _v25_version_for_runtime_row(self.db, r, addr),
            str(r['NUMPRIB'] or ''),
            _short_typevar(r['TYPEVAR']),
            _v25_clean_object_number_for_main(self.db, r, addr),
            str(r['CODEDEF'] or '0'),
            str(r['PROTOCOL'] or ''),
        ]
    NativeLikeBasketExactApp._report_display_values = _v25_report_display_values  # type: ignore[name-defined]
except Exception:
    pass

# v25 print settings: what is shown in preview is what is printed.  Orientation,
# scale, font family and font size are applied to page canvases before preview,
# and the same page canvases are sent to the printer.
V25_FONT_CHOICES = ['Arial', 'Calibri', 'Tahoma', 'Segoe UI', 'Times New Roman']
V25_SCALE_CHOICES = ['70%','80%','90%','100%','110%','120%','130%','140%']
V25_FONT_SIZE_CHOICES = ['7','8','9','10','11','12','13','14']


def _v25_font_tuple(font_desc: Any, family: str, size_factor: float, min_size: int = 5):
    size = 9; weight = 'normal'; slant = 'roman'
    try:
        import tkinter.font as tkfont
        f = tkfont.Font(font=font_desc)
        size = abs(int(f.actual('size') or 9))
        weight = f.actual('weight') or 'normal'
        slant = f.actual('slant') or 'roman'
    except Exception:
        try:
            parts = str(font_desc or '').split()
            for p in parts:
                if p.lstrip('-').isdigit():
                    size = abs(int(p)); break
            if 'bold' in str(font_desc).lower(): weight = 'bold'
            if 'italic' in str(font_desc).lower(): slant = 'italic'
        except Exception:
            pass
    return (family or 'Arial', max(min_size, int(round(size * float(size_factor)))), weight, slant)


def _v25_apply_page_font(page: tk.Canvas, family: str = 'Arial', size_factor: float = 1.0) -> None:
    try:
        for item in page.find_all():
            try:
                typ = page.type(item)
                if typ == 'text':
                    page.itemconfigure(item, font=_v25_font_tuple(page.itemcget(item,'font'), family, size_factor))
                elif typ == 'window':
                    win_name = page.itemcget(item, 'window')
                    if win_name:
                        child = page.nametowidget(win_name)
                        if isinstance(child, tk.Canvas):
                            _v25_apply_page_font(child, family, size_factor)
            except Exception:
                pass
    except Exception:
        pass


def _v25_make_pages(src: tk.Canvas, owner: tk.Misc, orientation: str='portrait', scale_pct: int=100, font_family: str='Arial', font_size: int=9, margin: int=34) -> list[tk.Canvas]:
    # Use the existing v23 slicer so multi-page layout stays stable.  Then apply
    # user font settings to the actual canvases that will be previewed/printed.
    pages = _v23_make_pages(src, owner, orientation, scale_pct, margin)  # type: ignore[name-defined]
    size_factor = max(0.55, min(2.0, float(font_size) / 9.0))
    for pg in pages:
        _v25_apply_page_font(pg, font_family, size_factor)
    return pages


def _v25_print_preview(owner: tk.Misc, canvas: Optional[tk.Canvas]=None, title: str='peleng_sheet') -> None:
    try:
        if canvas is None:
            canvas = getattr(owner, 'page_canvas', None)
        if not isinstance(canvas, tk.Canvas):
            try: canvas = _v19_make_report_print_canvas(owner)  # type: ignore[name-defined]
            except Exception: canvas = None
        if not isinstance(canvas, tk.Canvas):
            messagebox.showerror('Печать','Не найден Canvas листа для печати',parent=owner); return
        win = tk.Toplevel(owner); win.title('Предпросмотр печати A4'); win.geometry('1060x850')
        top = ttk.Frame(win,padding=6); top.pack(fill=tk.X)
        printers = _v17_enum_printers() if '_v17_enum_printers' in globals() else []  # type: ignore[name-defined]
        default_prn = _v17_default_printer() if '_v17_default_printer' in globals() else ''  # type: ignore[name-defined]
        ttk.Label(top,text='Принтер:').pack(side=tk.LEFT,padx=(0,4))
        prn_var=tk.StringVar(value=default_prn or (printers[0] if printers else ''))
        ttk.Combobox(top,textvariable=prn_var,values=printers,width=32,state=('readonly' if printers else 'normal')).pack(side=tk.LEFT,padx=4)
        ttk.Label(top,text='Ориентация:').pack(side=tk.LEFT,padx=(8,4))
        orient_var=tk.StringVar(value='Альбомная' if isinstance(owner, NativeReportSheet) else 'Книжная')
        orient_box=ttk.Combobox(top,textvariable=orient_var,values=['Книжная','Альбомная'],width=10,state='readonly'); orient_box.pack(side=tk.LEFT)
        ttk.Label(top,text='Масштаб:').pack(side=tk.LEFT,padx=(8,4))
        scale_var=tk.StringVar(value='100%')
        scale_box=ttk.Combobox(top,textvariable=scale_var,values=V25_SCALE_CHOICES,width=7,state='readonly'); scale_box.pack(side=tk.LEFT)
        ttk.Label(top,text='Шрифт:').pack(side=tk.LEFT,padx=(8,4))
        font_var=tk.StringVar(value='Arial')
        font_box=ttk.Combobox(top,textvariable=font_var,values=V25_FONT_CHOICES,width=13,state='readonly'); font_box.pack(side=tk.LEFT)
        ttk.Label(top,text='Размер:').pack(side=tk.LEFT,padx=(8,4))
        fsize_var=tk.StringVar(value='9')
        fsize_box=ttk.Combobox(top,textvariable=fsize_var,values=V25_FONT_SIZE_CHOICES,width=4,state='readonly'); fsize_box.pack(side=tk.LEFT)
        page_label=tk.StringVar(value='')
        body=tk.Canvas(win,bg='#555',highlightthickness=0); body.pack(fill=tk.BOTH,expand=True,side=tk.LEFT)
        vsb=ttk.Scrollbar(win,orient=tk.VERTICAL,command=body.yview); vsb.pack(side=tk.RIGHT,fill=tk.Y); body.configure(yscrollcommand=vsb.set)
        state={'pages':[], 'idx':0, 'view_zoom':0.72}
        def rebuild(*_):
            try: pct=int(scale_var.get().rstrip('%'))
            except Exception: pct=100
            try: fs=int(fsize_var.get())
            except Exception: fs=9
            orient='landscape' if orient_var.get().startswith('А') else 'portrait'
            state['pages']=_v25_make_pages(canvas, body, orient, pct, font_var.get(), fs)
            state['idx']=min(state['idx'], max(0,len(state['pages'])-1))
            show()
        def show():
            body.delete('all')
            pages=state.get('pages') or []
            if not pages: return
            pg=pages[state['idx']]
            z=state.get('view_zoom',0.72)
            view=tk.Canvas(body,bg='white',width=int(float(pg.cget('width'))*z),height=int(float(pg.cget('height'))*z),bd=1,relief=tk.SOLID,highlightthickness=0)
            body.create_window(18,18,anchor='nw',window=view); body.configure(scrollregion=(0,0,int(float(pg.cget('width'))*z)+40,int(float(pg.cget('height'))*z)+40))
            _v23_clone_slice(pg, view, z, 0, 0, float(pg.cget('height')))  # type: ignore[name-defined]
            page_label.set(f"Стр. {state['idx']+1}/{len(pages)}")
        def prev(): state.__setitem__('idx',max(0,state['idx']-1)); show()
        def nextp(): state.__setitem__('idx',min(len(state['pages'])-1,state['idx']+1)); show()
        def do_print():
            # Print exactly the pages currently shown/rebuilt with chosen orientation,
            # scale and font settings.
            pages = state.get('pages') or []
            if not pages:
                rebuild(); pages = state.get('pages') or []
            if not _v23_print_pages_bitmap(pages, prn_var.get().strip(), title):  # type: ignore[name-defined]
                messagebox.showwarning('Печать','Прямая печать недоступна. Установите:\npython -m pip install pywin32 pillow',parent=win)
            else:
                messagebox.showinfo('Печать','Задание отправлено на принтер',parent=win)
        ttk.Button(top,text='◀',command=prev,width=3).pack(side=tk.LEFT,padx=(8,2))
        ttk.Label(top,textvariable=page_label,width=10).pack(side=tk.LEFT)
        ttk.Button(top,text='▶',command=nextp,width=3).pack(side=tk.LEFT,padx=2)
        ttk.Button(top,text='Печать',command=do_print).pack(side=tk.LEFT,padx=10)
        ttk.Button(top,text='Закрыть',command=win.destroy).pack(side=tk.RIGHT)
        for cb in (orient_box, scale_box, font_box, fsize_box):
            cb.bind('<<ComboboxSelected>>', rebuild)
        rebuild()
    except Exception as exc:
        messagebox.showerror('Печать',str(exc),parent=owner)

# Override all existing preview hooks.
try:
    _v17_print_preview = _v25_print_preview  # type: ignore[assignment]
    _v18_print_preview = _v25_print_preview  # type: ignore[assignment]
    _v19_print_preview = _v25_print_preview  # type: ignore[assignment]
    _v20_print_preview = _v25_print_preview  # type: ignore[assignment]
    _v21_print_preview = _v25_print_preview  # type: ignore[assignment]
    _v22_print_preview = _v25_print_preview  # type: ignore[assignment]
    _v23_print_preview = _v25_print_preview  # type: ignore[assignment]
    _v17_wrap_buttons(NativeReportSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(NativeAscanProtocolSheet)  # type: ignore[name-defined]
    _v17_wrap_buttons(SettingDetail)  # type: ignore[name-defined]
except Exception:
    pass

# Runtime basket/raw DB is persisted next to the EXE/script so restart uses the
# same raw_records/idx_catalog data and opens the same UI as a fresh raw collect.
IDX_DB_DEFAULT = os.path.join(V23_SCRIPT_DIR, "peleng_vagon643_basket.sqlite3")


# ---------------------------------------------------------------------------
# v25 final runtime wiring
# ---------------------------------------------------------------------------
def install_latest_v25_overrides() -> None:
    """Install only the latest v25 implementations before the GUI is created.

    The historical upload accumulated v10..v25 fixes as many scattered runtime
    assignments.  This function is the single authoritative wiring point for
    the final version: every overridden class method/global hook is rebound to
    the newest implementation available in the file, and intermediate patch
    versions are intentionally skipped.
    """
    global decode_nastr2_params_643
    global _v17_save_postscript, _v19_clean_db_path, _v19_clean_connect
    global _v19_sync_clean_report, _v19_sync_clean_protocol, _v19_sync_clean_setting
    global _v19_clone_canvas_items, _v19_a4_canvas_from, _v20_a4_canvas_from
    global _v17_print_preview, _v18_print_preview, _v19_print_preview
    global _v20_print_preview, _v21_print_preview, _v22_print_preview, _v23_print_preview
    global IDX_DB_DEFAULT, _v23_save_ini, _v23_load_ini, _v23_clean_connect
    global _v23_sync_clean_report, _v23_sync_clean_protocol, _v23_sync_clean_setting

    _v23_load_ini = _v25_load_ini_cached
    _v23_save_ini = _v25_save_ini_preserve_runtime
    _v23_clean_connect = _v25_clean_connect_compact
    _v23_sync_clean_report = _v25_sync_clean_report
    _v23_sync_clean_protocol = _v25_sync_clean_protocol
    _v23_sync_clean_setting = _v25_sync_clean_setting
    storage_cfg = _v25_ensure_runtime_storage_config()
    IDX_DB_DEFAULT = storage_cfg["runtime_sqlite_path"]

    # Decode/storage helpers: final versions from v11/v20/v23.
    decode_nastr2_params_643 = _v11_decode_nastr2_params_643
    _v19_clean_db_path = _v20_user_db_path
    _v19_clean_connect = _v23_clean_connect
    _v20_clean_connect = _v23_clean_connect
    _v19_sync_clean_report = _v23_sync_clean_report
    _v19_sync_clean_protocol = _v23_sync_clean_protocol
    _v19_sync_clean_setting = _v23_sync_clean_setting
    _v17_save_postscript = _v19_save_postscript
    _v19_clone_canvas_items = _v20_clone_canvas_items
    _v19_a4_canvas_from = _v22_a4_canvas_from
    _v20_a4_canvas_from = _v22_a4_canvas_from

    # Main basket/app methods: latest report grid fix + latest protocol opener.
    NativeLikeBasketExactApp.open_selected_detail = _v18_open_selected_detail
    NativeLikeBasketExactApp._fetch_and_decode_addr = _v14_fetch_and_decode_addr
    NativeLikeBasketExactApp._protocol_display_values = _v14_protocol_display_values
    NativeLikeBasketExactApp._setting_display_values = _v14_setting_display_values
    NativeLikeBasketExactApp._report_display_values = _v25_report_display_values
    NativeLikeBasketExactApp.open_report_fields_settings = _ui_open_report_fields_settings
    NativeLikeBasketExactApp._after_report_fields_saved = _ui_after_report_fields_saved
    NativeLikeBasketExactApp.open_pg_settings = _v16_pg_open_settings
    NativeLikeBasketExactApp.export_selected_to_postgres = _ui_pg_export_selected
    NativeLikeBasketExactApp.export_all_to_postgres = _ui_pg_export_all
    NativeLikeBasketExactApp._worker_get_data = _v25_worker_get_data_parallel
    NativeLikeBasketExactApp.reload_idx_tables = _v25_reload_idx_tables_fast
    NativeLikeBasketExactApp._report_container_values = _v25_report_container_values_fast

    # Database persistence hooks: save decoded rows and then sync clean SQLite.
    PelengDB.save_report = _v19_save_report
    PelengDB.save_protocol = _v19_save_protocol
    PelengDB.save_setting = _v19_save_setting

    # Report/protocol/settings sheets: final drawing and decoding methods.
    NativeReportSheet.__init__ = _v19_report_init
    NativeReportSheet._build = _v25_report_sheet_build_fast
    NativeReportSheet.export_to_postgres = _report_sheet_export_to_pg
    NativeReportSheetBasketExact.export_to_postgres = _report_sheet_export_to_pg

    NativeAscanProtocolSheet._decode_setting_params = _v12_decode_setting_params
    NativeAscanProtocolSheet._decode_graph = _v21_decode_graph
    NativeAscanProtocolSheet._decode_defect = _v14_decode_defect
    NativeAscanProtocolSheet._typevar_info = _v12_sheet_typevar_info
    NativeAscanProtocolSheet._object_number_value = _v12_object_number_value
    NativeAscanProtocolSheet._smelting_value = _v12_smelting_value
    NativeAscanProtocolSheet._factory_value = _v12_factory_value
    NativeAscanProtocolSheet._year_value = _v12_year_value
    NativeAscanProtocolSheet._side_value = _v12_side_value
    NativeAscanProtocolSheet._neck_value = _v12_neck_value
    NativeAscanProtocolSheet._build = _v15_protocol_build
    NativeAscanProtocolSheet._draw_native_graph = _v21_draw_native_graph

    # Native-like settings sheet: compact latest v23 page with v22 builder.
    NativeSettingSheet.PAGE_W = 700
    NativeSettingSheet.PAGE_H = 900
    SettingDetail.PAGE_W = 700
    SettingDetail.PAGE_H = 900
    NativeSettingSheet.__init__ = _v23_setting_init
    SettingDetail.__init__ = _v23_setting_init
    NativeSettingSheet._build = _v22_setting_build
    SettingDetail._build = _v22_setting_build
    NativeSettingSheet._draw = _v23_setting_draw
    SettingDetail._draw = _v23_setting_draw

    ReportFieldsSettingsDialog._build = _v23_report_settings_build
    ReportFieldsSettingsDialog._save = _v23_report_settings_save
    PostgresSettingsDialog.save = _v25_pg_dialog_save

    # WYSIWYG print is the final v25 preview path. Re-wrap buttons once after
    # assigning every preview alias so old lambdas open the same final preview.
    _v17_print_preview = _v25_print_preview
    _v18_print_preview = _v25_print_preview
    _v19_print_preview = _v25_print_preview
    _v20_print_preview = _v25_print_preview
    _v21_print_preview = _v25_print_preview
    _v22_print_preview = _v25_print_preview
    _v23_print_preview = _v25_print_preview
    for _sheet_cls in (NativeReportSheet, NativeAscanProtocolSheet, SettingDetail):
        try:
            _v17_wrap_buttons(_sheet_cls)
        except Exception:
            pass



# ---------------------------------------------------------------------------
# v25 portable storage
# ---------------------------------------------------------------------------
V25_DEFAULT_RUNTIME_DB = _portable_existing_file("peleng_vagon643_basket.sqlite3") or os.path.join(V23_SCRIPT_DIR, "peleng_vagon643_basket.sqlite3")
V25_DEFAULT_ARCHIVE_DIR = os.path.join(V23_SCRIPT_DIR, "raw_archives")


def _v25_runtime_storage_defaults() -> dict[str, str]:
    return {
        "runtime_sqlite_path": V25_DEFAULT_RUNTIME_DB,
        "archive_dir": V25_DEFAULT_ARCHIVE_DIR,
        "auto_archive": "yes",
    }


def _v25_ensure_runtime_storage_config() -> dict[str, str]:
    """Create/update settings.ini for decoded SQLite, persistent basket and RAW ZIP archives.

    The basket/raw SQLite is intentionally persistent: it stores raw_records,
    raw_events and idx_catalog so an EXE restart can rebuild the same UI and
    decode from raw data instead of copying rows from the compact decoded DB.
    """
    defaults = _v25_runtime_storage_defaults()
    cp = _v23_configparser.ConfigParser() if _v23_configparser is not None else None
    if cp is None:
        os.makedirs(defaults["archive_dir"], exist_ok=True)
        return defaults
    try:
        if os.path.exists(V23_SETTINGS_INI):
            cp.read(V23_SETTINGS_INI, encoding="utf-8")
        if not cp.has_section("sqlite"):
            cp.add_section("sqlite")
        if not cp.get("sqlite", "path", fallback="").strip():
            cp.set("sqlite", "path", V23_DEFAULT_DECODED_DB)
        if not cp.has_section("runtime"):
            cp.add_section("runtime")
        runtime_path = cp.get("runtime", "sqlite_path", fallback="").strip()
        if not runtime_path or runtime_path == ":memory:":
            cp.set("runtime", "sqlite_path", defaults["runtime_sqlite_path"])
        if not cp.get("runtime", "archive_dir", fallback="").strip():
            cp.set("runtime", "archive_dir", defaults["archive_dir"])
        if not cp.get("runtime", "auto_archive", fallback="").strip():
            cp.set("runtime", "auto_archive", defaults["auto_archive"])
        os.makedirs(os.path.dirname(V23_SETTINGS_INI) or ".", exist_ok=True)
        with open(V23_SETTINGS_INI, "w", encoding="utf-8") as f:
            cp.write(f)
        _v25_invalidate_ini_cache()
    except Exception:
        pass

    runtime_path = cp.get("runtime", "sqlite_path", fallback=defaults["runtime_sqlite_path"]).strip() or defaults["runtime_sqlite_path"]
    if runtime_path == ":memory:":
        runtime_path = defaults["runtime_sqlite_path"]
    runtime_path = _portable_resolve_data_path(runtime_path, os.path.basename(defaults["runtime_sqlite_path"]))
    archive_dir = cp.get("runtime", "archive_dir", fallback=defaults["archive_dir"]).strip() or defaults["archive_dir"]
    archive_dir = os.path.abspath(os.path.expanduser(archive_dir))
    os.makedirs(archive_dir, exist_ok=True)
    auto_archive = cp.get("runtime", "auto_archive", fallback=defaults["auto_archive"]).strip().lower()
    return {"runtime_sqlite_path": runtime_path, "archive_dir": archive_dir, "auto_archive": auto_archive}



def _v25_save_ini_preserve_runtime(cfg: dict[str, Any]) -> None:
    """Save report/decoded DB settings without dropping runtime/PostgreSQL sections."""
    if _v23_configparser is None:
        return
    cp = _v23_configparser.ConfigParser()
    try:
        if os.path.exists(V23_SETTINGS_INI):
            cp.read(V23_SETTINGS_INI, encoding="utf-8")
    except Exception:
        pass
    if not cp.has_section("sqlite"):
        cp.add_section("sqlite")
    cp.set("sqlite", "path", str(cfg.get("sqlite_path") or V23_DEFAULT_DECODED_DB))
    if not cp.has_section("report"):
        cp.add_section("report")
    cp.set("report", "enterprise", str(cfg.get("enterprise") or ""))
    cp.set("report", "subdivision", str(cfg.get("subdivision") or ""))
    if cp.has_section("operators"):
        cp.remove_section("operators")
    cp.add_section("operators")
    for k, v in dict(cfg.get("operators") or {}).items():
        if str(k).strip():
            cp.set("operators", str(k).strip(), str(v).strip())
    if not cp.has_section("runtime"):
        cp.add_section("runtime")
    defaults = _v25_runtime_storage_defaults()
    runtime_path = cp.get("runtime", "sqlite_path", fallback="").strip()
    if not runtime_path or runtime_path == ":memory:":
        runtime_path = defaults["runtime_sqlite_path"]
    cp.set("runtime", "sqlite_path", runtime_path)
    if not cp.get("runtime", "archive_dir", fallback="").strip():
        cp.set("runtime", "archive_dir", defaults["archive_dir"])
    if not cp.get("runtime", "auto_archive", fallback="").strip():
        cp.set("runtime", "auto_archive", defaults["auto_archive"])
    os.makedirs(os.path.dirname(V23_SETTINGS_INI) or ".", exist_ok=True)
    with open(V23_SETTINGS_INI, "w", encoding="utf-8") as f:
        cp.write(f)
    _v25_invalidate_ini_cache()


def _v25_restore_idx_catalog_from_raw(db: PelengDB) -> int:
    """Rebuild a visible basket catalogue if a persistent raw DB lacks idx rows."""
    try:
        has_idx = db.conn.execute("SELECT count(*) AS c FROM idx_catalog").fetchone()["c"]
        if has_idx:
            return 0
        rows = list(db.conn.execute("SELECT * FROM raw_records ORDER BY address"))
    except Exception:
        return 0
    if not rows:
        return 0
    session_id = dt.datetime.now().strftime("restored_%Y%m%d_%H%M%S")
    created = PelengDB.now()
    for i, row in enumerate(rows):
        addr = int(row["address"])
        db.conn.execute(
            """
            INSERT INTO idx_catalog(session_id,created_at,source_order,address,bucket,kind,expected_len,requested,decoded,raw_len,status,summary,header_hex)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                session_id,
                created,
                i,
                addr,
                bucket_for_addr(addr),
                kind_for_addr(addr),
                expected_len_for_addr(addr),
                1,
                1 if db.row_by_addr("reports", addr) or db.row_by_addr("protocols", addr) or db.row_by_addr("settings", addr) else 0,
                int(row["raw_len"] or 0),
                "restored from persistent raw",
                "восстановлено из SQLite",
                str(row["header_hex"] or ""),
            ),
        )
    db.conn.commit()
    return len(rows)


def _v25_archive_runtime_raw(app: Any, reason: str = "bulk") -> str:
    """Write a timestamped raw ZIP archive for the current persistent basket DB."""
    cfg = _v25_ensure_runtime_storage_config()
    if str(cfg.get("auto_archive") or "yes").lower() in ("0", "no", "false", "off"):
        return ""
    try:
        raw_count = app.db.conn.execute("SELECT count(*) AS c FROM raw_records").fetchone()["c"]
    except Exception:
        raw_count = 0
    if not raw_count:
        return ""
    session = str(getattr(app, "session_id", "") or dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    safe_session = re.sub(r"[^0-9A-Za-z_.-]+", "_", session)
    fname = f"peleng_raw_{safe_session}_{reason}.zip"
    path = os.path.join(str(cfg["archive_dir"]), fname)
    app.db.export_raw_zip(path)
    return path



# ---------------------------------------------------------------------------
# v25 compact decoded SQLite schema
# ---------------------------------------------------------------------------
V25_CLEAN_SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "reports": [
        ("record_type", "TEXT"), ("control_date", "TEXT"), ("control_time", "TEXT"),
        ("device_no", "TEXT"), ("software_version", "TEXT"), ("enterprise", "TEXT"),
        ("subdivision", "TEXT"), ("operator_code", "TEXT"), ("operator_name", "TEXT"),
        ("setting_no", "TEXT"), ("object_type", "TEXT"), ("object_number", "TEXT"),
        ("smelting", "TEXT"), ("factory", "TEXT"), ("production_year", "TEXT"),
        ("side", "TEXT"), ("neck", "TEXT"), ("rim", "TEXT"), ("wheel_turning", "TEXT"),
        ("crest", "TEXT"), ("defects_count", "TEXT"), ("protocol", "TEXT"),
    ],
    "protocols": [
        ("record_type", "TEXT"), ("control_date", "TEXT"), ("control_time", "TEXT"),
        ("device_no", "TEXT"), ("software_version", "TEXT"), ("enterprise", "TEXT"),
        ("subdivision", "TEXT"), ("operator_code", "TEXT"), ("operator_name", "TEXT"),
        ("setting_no", "TEXT"), ("object_type", "TEXT"), ("object_number", "TEXT"),
        ("smelting", "TEXT"), ("factory", "TEXT"), ("production_year", "TEXT"),
        ("side", "TEXT"), ("neck", "TEXT"), ("detail", "TEXT"), ("conclusion", "TEXT"),
        ("defect_m", "TEXT"), ("defect_y", "TEXT"), ("defect_x", "TEXT"),
        ("defect_r", "TEXT"), ("defect_detectability", "TEXT"),
    ],
    "settings": [
        ("record_type", "TEXT"), ("setting_no", "TEXT"), ("setting_date", "TEXT"),
        ("setting_time", "TEXT"), ("device_no", "TEXT"), ("software_version", "TEXT"),
        ("operator_code", "TEXT"), ("object_type", "TEXT"), ("freq_mhz", "TEXT"),
        ("sound_speed", "TEXT"), ("thickness_mm", "TEXT"), ("amplitude_probe", "TEXT"),
        ("cutoff_pct", "TEXT"), ("blocking", "TEXT"), ("probe_no", "TEXT"),
        ("probe_enabled", "TEXT"), ("angle_deg", "TEXT"), ("probe_time_us", "TEXT"),
        ("gain_db", "TEXT"), ("required_sens_db", "TEXT"), ("actual_sens_db", "TEXT"),
        ("extra_gain_db", "TEXT"), ("sweep_type", "TEXT"), ("sweep_duration", "TEXT"),
        ("sweep_delay", "TEXT"), ("w_sweep_enabled", "TEXT"), ("envelope_enabled", "TEXT"),
        ("so_start", "TEXT"), ("so_end", "TEXT"), ("vs1_start", "TEXT"),
        ("vs1_end", "TEXT"), ("vs1_method", "TEXT"), ("vs1_threshold_pct", "TEXT"),
        ("vs2_start", "TEXT"), ("vs2_end", "TEXT"), ("vs2_method", "TEXT"),
        ("vs2_threshold_pct", "TEXT"), ("aru_enabled", "TEXT"), ("aru_start", "TEXT"),
        ("aru_end", "TEXT"), ("vrch_type", "TEXT"), ("vrch_indication", "TEXT"),
        ("vrch_start", "TEXT"), ("vrch_end", "TEXT"), ("vrch_amplitude_db", "TEXT"),
        ("vrch_shape", "TEXT"), ("before_vrch_db", "TEXT"), ("after_vrch_db", "TEXT"),
        ("extra_gain_enabled", "TEXT"),
    ],
}


def _v25_typevar_text(value: Any) -> str:
    try:
        return _v19_typevar_text(value)  # type: ignore[name-defined]
    except Exception:
        try:
            return str(typevar_display(int(_short_typevar(value))))
        except Exception:
            return str(value or "")


_v25_clean_schema_ready: set[str] = set()



def _v25_payload_version_from_record(record: bytes, addr: int, fallback: Any = "") -> str:
    """Prefer the firmware version that is physically present in a record payload."""
    raw = bytes(record or b"")
    candidates: list[str] = []
    if raw:
        try:
            if kind_for_addr(int(addr)) in ("report", "report_v2"):
                body, _layout = report_body_and_layout(raw, int(addr))
                candidates.append(_fw_string_from_payload(body, ""))
        except Exception:
            pass
        candidates.append(_fw_string_from_payload(raw, ""))
    candidates.append(str(fallback or ""))
    for v in candidates:
        s = str(v or "").strip()
        if s and s not in ("6.43", "06.43"):
            return s
    for v in candidates:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _v25_payload_version_from_db(db: Any, addr: int, fallback: Any = "") -> str:
    """Prefer firmware version decoded from raw payload; fallback to row/header."""
    versions: list[str] = []
    try:
        rr = db.get_raw_by_addr(int(addr)) if db is not None else None
        raw = bytes(rr["raw"]) if rr else b""
        if raw:
            versions.append(_v25_payload_version_from_record(raw, int(addr), ""))
    except Exception:
        pass
    try:
        h = _report_header_for_addr(db, int(addr)) if db is not None else b""
        if h:
            versions.append(_native_header_version(h))
    except Exception:
        pass
    versions.append(str(fallback or ""))
    for v in versions:
        s = str(v or "").strip()
        if s and s not in ("6.43", "06.43"):
            return s
    for v in versions:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _v25_version_for_runtime_row(db: Any, row: sqlite3.Row | None, addr: int) -> str:
    fallback = ""
    try:
        fallback = str(row["NUMVERS"] or "") if row is not None and "NUMVERS" in row.keys() else ""
    except Exception:
        fallback = ""
    return _v25_payload_version_from_db(db, int(addr), fallback) or fallback


def _v25_clean_connect_compact(db: Any = None):
    """Open decoded SQLite with exactly three useful tables and compact columns."""
    path = _portable_resolve_data_path(_v20_user_db_path(db))
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    ready_key = os.path.abspath(path)
    if ready_key in _v25_clean_schema_ready:
        return conn
    keep = set(V25_CLEAN_SCHEMAS)
    for row in list(conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")):
        name = str(row["name"])
        if name not in keep:
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
    for table, cols in V25_CLEAN_SCHEMAS.items():
        ddl_cols = ",".join(f'"{name}" {typ}' for name, typ in cols)
        expected = [name for name, _typ in cols]
        existing = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        if not existing:
            conn.execute(f'CREATE TABLE "{table}" ({ddl_cols})')
        elif existing != expected:
            tmp = f"__{table}_compact"
            conn.execute(f'DROP TABLE IF EXISTS "{tmp}"')
            conn.execute(f'CREATE TABLE "{tmp}" ({ddl_cols})')
            common = [c for c in expected if c in existing]
            if common:
                col_list = ",".join(f'"{c}"' for c in common)
                conn.execute(f'INSERT INTO "{tmp}" ({col_list}) SELECT {col_list} FROM "{table}"')
            conn.execute(f'DROP TABLE "{table}"')
            conn.execute(f'ALTER TABLE "{tmp}" RENAME TO "{table}"')
    conn.commit()
    _v25_clean_schema_ready.add(ready_key)
    return conn




def _v25_insert_clean(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    cols = [name for name, _typ in V25_CLEAN_SCHEMAS[table]]
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f'INSERT INTO "{table}" ({",".join(cols)}) VALUES({placeholders})',
        [str(values.get(c) or "") for c in cols],
    )


def _v25_sync_clean_report(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("reports", int(addr))
        if not row:
            return
        vals = _native_report_detail_values(db, row)  # type: ignore[name-defined]
        operator_code = str(row["KODOPERA"] or "") if "KODOPERA" in row.keys() else ""
        tv = row["TYPEVAR"] if "TYPEVAR" in row.keys() else vals.get("obj_type")
        object_type = str(vals.get("obj_type") or _v25_typevar_text(tv))
        conn = _v25_clean_connect_compact(db)
        with conn:
            _v25_insert_clean(conn, "reports", {
                "record_type": "Отчёт контроля", "control_date": vals.get("date"), "control_time": vals.get("time"),
                "device_no": row["NUMPRIB"] if "NUMPRIB" in row.keys() else "", "software_version": _v25_payload_version_from_db(db, int(addr), row["NUMVERS"] if "NUMVERS" in row.keys() else ""),
                "enterprise": _report_enterprise(), "subdivision": _report_subdivision(), "operator_code": operator_code,
                "operator_name": _operator_name_for_code(operator_code, str(row["NAMEOPERA"] or "") if "NAMEOPERA" in row.keys() else ""),
                "setting_no": vals.get("setting_no"), "object_type": object_type, "object_number": vals.get("numobj"),
                "smelting": vals.get("smelting"), "factory": vals.get("factory"), "production_year": vals.get("year"),
                "side": vals.get("side"), "neck": vals.get("neck"), "rim": vals.get("rim"), "wheel_turning": vals.get("wheel_turn"),
                "crest": vals.get("crest"), "defects_count": vals.get("defects"), "protocol": row["PROTOCOL"] if "PROTOCOL" in row.keys() else "",
            })
        conn.close()
    except Exception:
        pass


def _v25_sync_clean_protocol(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("protocols", int(addr))
        rr = db.get_raw_by_addr(int(addr))
        raw = bytes(rr["raw"]) if rr else b""
        if not row:
            return
        vals = _v19_protocol_values(db, row, raw)  # type: ignore[name-defined]
        operator_code = str(row["KODOPERA"] or "") if "KODOPERA" in row.keys() else ""
        conn = _v25_clean_connect_compact(db)
        with conn:
            _v25_insert_clean(conn, "protocols", {
                "record_type": "Протокол А-развёртки", "control_date": row["DATEFORM"] if "DATEFORM" in row.keys() else "",
                "control_time": row["TIMEFORM"] if "TIMEFORM" in row.keys() else "", "device_no": row["NUMPRIB"] if "NUMPRIB" in row.keys() else "",
                "software_version": _v25_payload_version_from_db(db, int(addr), row["NUMVERS"] if "NUMVERS" in row.keys() else ""), "enterprise": _report_enterprise(),
                "subdivision": _report_subdivision(), "operator_code": operator_code,
                "operator_name": _operator_name_for_code(operator_code, str(row["NAMEOPERA"] or "") if "NAMEOPERA" in row.keys() else ""),
                "setting_no": row["SETTING_NO"] if "SETTING_NO" in row.keys() else "", "object_type": vals.get("object_type"),
                "object_number": vals.get("object_number"), "smelting": vals.get("smelting"), "factory": vals.get("factory"),
                "production_year": vals.get("year"), "side": vals.get("side"), "neck": vals.get("neck"), "detail": vals.get("detail"),
                "conclusion": "Признак дефекта отсутствует", "defect_m": vals.get("defect_m"), "defect_y": vals.get("defect_y"),
                "defect_x": vals.get("defect_x"), "defect_r": vals.get("defect_r"), "defect_detectability": vals.get("defect_detectability"),
            })
        conn.close()
    except Exception:
        pass


def _v25_sync_clean_setting(db: Any, addr: int) -> None:
    try:
        row = db.row_by_addr("settings", int(addr))
        rr = db.get_raw_by_addr(int(addr))
        raw = bytes(rr["raw"]) if rr else b""
        if not row:
            return
        p = decode_nastr2_params_643(raw, int(addr)) if raw else {}  # type: ignore[name-defined]
        tv = p.get("typevar_code") or (row["TYPEVAR"] if "TYPEVAR" in row.keys() else "")
        conn = _v25_clean_connect_compact(db)
        with conn:
            _v25_insert_clean(conn, "settings", {
                "record_type": "Настройка", "setting_no": p.get("setting_no") or (int(addr)-1000 if 1000 <= int(addr) <= 1999 else int(addr)),
                "setting_date": p.get("date") or (row["DATEFORM"] if "DATEFORM" in row.keys() else ""),
                "setting_time": p.get("time") or (row["TIMEFORM"] if "TIMEFORM" in row.keys() else ""),
                "device_no": row["NUMPRIB"] if "NUMPRIB" in row.keys() else "", "software_version": _v25_payload_version_from_db(db, int(addr), row["NUMVERS"] if "NUMVERS" in row.keys() else ""),
                "operator_code": p.get("operator_code") or (row["KODOPERA"] if "KODOPERA" in row.keys() else ""), "object_type": _v25_typevar_text(tv),
                **{k: p.get(k) for k in ["freq_mhz", "sound_speed", "thickness_mm", "amplitude_probe", "cutoff_pct", "blocking", "probe_no", "probe_enabled", "angle_deg", "probe_time_us", "gain_db", "required_sens_db", "actual_sens_db", "extra_gain_db", "sweep_type", "sweep_duration", "sweep_delay", "w_sweep_enabled", "envelope_enabled", "so_start", "so_end", "vs1_start", "vs1_end", "vs1_method", "vs1_threshold_pct", "vs2_start", "vs2_end", "vs2_method", "vs2_threshold_pct", "aru_enabled", "aru_start", "aru_end", "vrch_type", "vrch_indication", "vrch_start", "vrch_end", "vrch_shape", "before_vrch_db", "after_vrch_db", "extra_gain_enabled"]},
                "vrch_amplitude_db": p.get("vrch_amp_db") or p.get("vrch_amplitude_db") or p.get("vrch_amplitude"),
            })
        conn.close()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# v25 stability/load-speed cleanup helpers
# ---------------------------------------------------------------------------
_v25_ini_cache: dict[str, Any] = {"mtime": None, "cfg": None}


def _v25_invalidate_ini_cache() -> None:
    _v25_ini_cache["mtime"] = None
    _v25_ini_cache["cfg"] = None


def _v25_load_ini_uncached() -> dict[str, Any]:
    """Load settings.ini once, preserving the v23 config shape."""
    cfg = _v23_ini_defaults()
    if _v23_configparser is None:
        return cfg
    cp = _v23_configparser.ConfigParser()
    try:
        if os.path.exists(V23_SETTINGS_INI):
            cp.read(V23_SETTINGS_INI, encoding="utf-8")
        if cp.has_section("sqlite"):
            path = cp.get("sqlite", "path", fallback=cfg["sqlite_path"]).strip()
            if path:
                cfg["sqlite_path"] = _portable_resolve_data_path(path)
        if cp.has_section("report"):
            cfg["enterprise"] = cp.get("report", "enterprise", fallback=cfg["enterprise"])
            cfg["subdivision"] = cp.get("report", "subdivision", fallback=cfg["subdivision"])
        ops: dict[str, str] = {}
        if cp.has_section("operators"):
            for k, v in cp.items("operators"):
                code = _normalize_operator_code(k) if "_normalize_operator_code" in globals() else str(k).strip()
                if code:
                    ops[code] = str(v).strip()
        cfg["operators"] = ops
    except Exception:
        pass
    return cfg


def _v25_load_ini_cached() -> dict[str, Any]:
    """Cached settings.ini reader used by table rendering and decoders.

    Several visible columns call `_operator_name_for_code()` for every basket
    row.  Without caching that re-parsed settings.ini once per row, which made
    reopening a persistent basket unnecessarily slow.
    """
    try:
        mtime = os.path.getmtime(V23_SETTINGS_INI) if os.path.exists(V23_SETTINGS_INI) else None
    except Exception:
        mtime = None
    cached = _v25_ini_cache.get("cfg")
    if cached is not None and _v25_ini_cache.get("mtime") == mtime:
        return dict(cached)
    cfg = _v25_load_ini_uncached()
    _v25_ini_cache["mtime"] = mtime
    _v25_ini_cache["cfg"] = dict(cfg)
    return dict(cfg)


def _v25_install_runtime_indexes(db: PelengDB) -> None:
    """Add indexes for the persistent basket workload; safe on old DB files."""
    try:
        db.conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_catalog_bucket_addr ON idx_catalog(bucket, address);
            CREATE INDEX IF NOT EXISTS idx_catalog_bucket_order ON idx_catalog(bucket, source_order, address);
            CREATE INDEX IF NOT EXISTS idx_catalog_header_present ON idx_catalog(header_hex) WHERE header_hex IS NOT NULL AND header_hex<>'';
            CREATE INDEX IF NOT EXISTS raw_events_address_id ON raw_events(address, id);
            CREATE INDEX IF NOT EXISTS protocol_diagnostics_address ON protocol_diagnostics(address);
        """)
        db.conn.commit()
    except Exception:
        pass


def _v25_bucket_counts(db: PelengDB) -> dict[str, int]:
    counts = {"reports": 0, "protocols": 0, "settings": 0, "other": 0}
    try:
        for row in db.conn.execute("SELECT bucket, count(*) AS c FROM idx_catalog GROUP BY bucket"):
            b = str(row["bucket"] or "other")
            counts[b if b in counts else "other"] += int(row["c"] or 0)
    except Exception:
        pass
    return counts


def _v25_report_container_map_fast(db: PelengDB) -> list[dict[str, Any]]:
    """Build report containers with decoded representative rows prefetched."""
    rows = list(db.conn.execute("SELECT * FROM idx_catalog WHERE bucket='reports' ORDER BY source_order, address"))
    if not rows:
        return []
    report_rows = {int(r["address"]): r for r in db.conn.execute("SELECT * FROM reports ORDER BY address")}
    by_base: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for row in rows:
        addr = int(row["address"])
        base = native_report_container_base(addr)
        c = by_base.get(base)
        if c is None:
            c = {"base": base, "first_addr": addr, "first_order": int(row["source_order"]), "rows": [], "report_row": None, "report_addr": addr}
            by_base[base] = c
            order.append(base)
        c["rows"].append(row)
        if int(row["source_order"]) < int(c["first_order"]):
            c["first_addr"] = addr
            c["first_order"] = int(row["source_order"])
        if c.get("report_row") is None and addr in report_rows:
            c["report_row"] = report_rows[addr]
            c["report_addr"] = addr
    return [by_base[b] for b in order]


def _v25_report_container_values_fast(self: NativeLikeBasketExactApp, container: dict[str, Any]) -> list[str]:
    children = list(container.get("rows") or [])
    rep_addr = int(container.get("report_addr") or container.get("first_addr") or 0)
    report_row = container.get("report_row")
    if report_row is None and children:
        rep_addr, report_row = _best_report_row_for_container(self.db, children)
    if report_row:
        vals = self._report_display_values(report_row)
        h = _report_header_for_addr(self.db, rep_addr)
        dev = _native_header_device(h) if h else ""
        if dev:
            vals[5] = dev
    else:
        vals = [native_visible_num_for_addr(rep_addr), "", "", "", "", "", "", "", "", ""]
    return vals



def _v25_report_sheet_build_fast(self: NativeReportSheet) -> None:
    """Old native Tk-label report sheet, but rendered in small UI batches.

    The visible sheet is again the original white page made from Tk widgets.
    To avoid the old freeze on large baskets we create rows incrementally with
    `after()`, so the window appears immediately and scrolling remains usable.
    """
    top_menu = ttk.Frame(self)
    top_menu.pack(fill=tk.X)
    for t in ("Печать", "Сохранить", "Настройка"):
        ttk.Button(top_menu, text=t).pack(side=tk.LEFT, padx=(4, 2), pady=3)
    ttk.Button(top_menu, text="В PostgreSQL", command=self.export_to_postgres).pack(side=tk.LEFT, padx=(12, 2), pady=3)

    outer = tk.Frame(self, bg="#d8d8d8")
    outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))
    canvas = tk.Canvas(outer, bg="#d8d8d8", highlightthickness=0)
    vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    hsb = ttk.Scrollbar(outer, orient=tk.HORIZONTAL, command=canvas.xview)
    canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    outer.rowconfigure(0, weight=1)
    outer.columnconfigure(0, weight=1)

    page = tk.Frame(canvas, bg="white", bd=1, relief=tk.SOLID)
    canvas.create_window((20, 20), window=page, anchor="nw")
    page.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

    rows = self._rows_for_group()
    first = rows[0] if rows else None
    first_vals = _native_report_detail_values(self.db, first) if first else {}
    device = str(first["NUMPRIB"] if first and "NUMPRIB" in first.keys() else "")
    version = _v25_version_for_runtime_row(self.db, first, int(first["address"])) if first and "address" in first.keys() else "06.43"
    ntd = "СТО РЖД 1.11.002-2008 (ТИ 07.73-2009)"
    try:
        tv = int(_short_typevar(first["TYPEVAR"])) if first else 0
        info = typevar_info_643(tv)
        ntd = info.get("ntd") or ntd
    except Exception:
        pass

    tk.Label(page, text=f"ОТЧЕТ № {self.group_base % 10000 // 100 if self.group_base else self.selected_addr % 10000}", bg="white", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 0))
    tk.Label(page, text=f"о контроле дефектоскопом УД2-102 № {device or '----'}, Версия {version or '6.43'}", bg="white", font=("Arial", 9)).grid(row=1, column=0, sticky="w", padx=18)

    info_frame = tk.Frame(page, bg="white")
    info_frame.grid(row=2, column=0, sticky="ew", padx=18, pady=(16, 12))
    operator_code = str(first["KODOPERA"] if first else "")
    operator_name = _operator_name_for_code(operator_code)
    left = [
        ("Предприятие", _report_enterprise()), ("Подразделение", _report_subdivision()),
        ("Оператор: шифр", operator_code), ("Фамилия", operator_name),
        ("НТД на контроль", ntd), ("Номер настройки", str(first_vals.get("setting_no", ""))),
    ]
    for r, (k, v) in enumerate(left):
        tk.Label(info_frame, text=k, bg="white", font=("Arial", 9), anchor="w", width=18).grid(row=r, column=0, sticky="w")
        tk.Label(info_frame, text=v, bg="white", font=("Arial", 11, "bold" if r in (0, 1, 3, 4) else "normal"), anchor="w", width=52).grid(row=r, column=1, sticky="w")

    table = tk.Frame(page, bg="white")
    table.grid(row=3, column=0, sticky="nw", padx=18, pady=(6, 18))
    cols = ["№", "Дата", "Объект: тип", "Номер объекта", "Плавка", "З-д", "Год", "Стор", "шейка", "обод", "обт. колес", "нал. гребня", "к-во деф"]
    widths = [4, 14, 18, 14, 9, 7, 6, 7, 13, 12, 11, 11, 8]
    for c, title in enumerate(cols):
        tk.Label(table, text=title, bg="#efefef", bd=1, relief=tk.SOLID, font=("Arial", 8, "bold"), width=widths[c], anchor="center").grid(row=0, column=c, sticky="nsew")

    progress_var = tk.StringVar(value=f"Загрузка строк отчёта: 0/{len(rows)}")
    progress = ttk.Label(self, textvariable=progress_var, anchor="w")
    progress.pack(fill=tk.X, padx=12, pady=(0, 8))
    row_cache: list[dict[str, Any] | None] = [None] * len(rows)

    def render_batch(start: int = 0, batch: int = 20) -> None:
        stop = min(len(rows), start + batch)
        for i in range(start, stop):
            row = rows[i]
            vals = _native_report_detail_values(self.db, row)
            row_cache[i] = vals
            line = [
                str(i + 1), _native_report_display_date(vals["date"]), vals["obj_type"], vals["numobj"], vals["smelting"], vals["factory"], vals["year"],
                vals["side"], vals["neck"], vals["rim"], vals["wheel_turn"], vals["crest"], vals["defects"],
            ]
            for c, val in enumerate(line):
                tk.Label(table, text=val, bg="white", bd=1, relief=tk.SOLID, font=("Arial", 8), width=widths[c], anchor="w" if c in (2, 8, 9, 10, 11) else "center").grid(row=i + 1, column=c, sticky="nsew")
        progress_var.set(f"Загрузка строк отчёта: {stop}/{len(rows)}")
        if stop < len(rows):
            self.after(1, lambda: render_batch(stop, batch))
        else:
            progress_var.set(f"Строк отчёта: {len(rows)}")
            tk.Label(page, text="Подпись:", bg="white", font=("Arial", 9)).grid(row=4, column=0, pady=(28, 30))

    self.page_canvas = None  # printing builds lazy canvas; visible sheet stays old Tk widgets
    self._report_rows_cache = row_cache
    self.after(1, render_batch)


def _v25_reload_idx_tables_fast(self: NativeLikeBasketExactApp) -> None:
    """Fast basket redraw for persistent DB startup and bulk-refresh batches."""
    tree = self.main_tree
    tree.delete(*tree.get_children())
    mode = self.mode_var.get()
    containers_cache: list[dict[str, Any]] | None = None

    if mode == "reports":
        containers_cache = _v25_report_container_map_fast(self.db)
        for c in containers_cache:
            base = int(c["base"])
            rep_addr = int(c["first_addr"])
            tags = (f"addr:{rep_addr}", f"base:{base}", f"children:{len(c.get('rows') or [])}")
            tree.insert("", tk.END, values=self._report_container_values(c), tags=tags)
    else:
        if mode == "protocols":
            buckets = ("protocols",)
        elif mode == "settings":
            buckets = ("settings",)
        else:
            buckets = ("reports", "protocols", "settings", "other")
        qmarks = ",".join("?" for _ in buckets)
        rows = list(self.db.conn.execute(f"SELECT * FROM idx_catalog WHERE bucket IN ({qmarks}) ORDER BY address", buckets)) if buckets else []
        if mode == "all":
            containers_cache = _v25_report_container_map_fast(self.db)
            for c in containers_cache:
                base = int(c["base"])
                rep_addr = int(c["first_addr"])
                tree.insert("", tk.END, values=self._report_container_values(c), tags=(f"addr:{rep_addr}", f"base:{base}"))
            rows = [r for r in rows if r["bucket"] != "reports"]
        for row in rows:
            addr = int(row["address"])
            if row["bucket"] == "protocols":
                vals = self._protocol_display_values(row)
            elif row["bucket"] == "settings":
                vals = self._setting_display_values(row)
            else:
                vals = [str(addr)] + [""] * (len(self._column_defs()) - 1)
            tree.insert("", tk.END, values=vals, tags=(f"addr:{addr}",))

    counts_raw = _v25_bucket_counts(self.db)
    if containers_cache is None:
        containers_cache = _v25_report_container_map_fast(self.db)

# ---------------------------------------------------------------------------
# v25 parallel collection pipeline
# ---------------------------------------------------------------------------
def _v25_decode_record_payload(packet: dict[str, Any]) -> dict[str, Any]:
    """CPU-only decode step for ThreadPoolExecutor workers.

    Serial I/O must stay ordered on one COM thread, and Tk widgets must stay on
    the Tk main thread.  The expensive binary decoding is independent once the
    raw record has been read, so this function intentionally has no DB or Tk
    side effects and can safely run in parallel worker threads.
    """
    addr = int(packet["addr"])
    record = bytes(packet.get("record") or b"")
    status = str(packet.get("status") or "")
    base_kind = str(packet.get("base_kind") or kind_for_addr(addr))
    device_no = packet.get("device_no")
    decoded = False
    fields: dict[str, str] = {}
    params: dict[str, Any] = {}
    summary = ""

    if status.startswith("ok"):
        try:
            if base_kind in ("report", "report_v2"):
                fields = decode_report_643(record, addr, device_no, strict=False)
                decoded = True
            elif base_kind in ("protocol_short", "protocol_graph"):
                fields = decode_protocol_ascan_643(record, addr, device_no, strict=False)
                decoded = True
            elif base_kind == "setting":
                fields, params = decode_setting_643(record, addr, device_no, strict=False)
                decoded = True
            elif base_kind == "bscan":
                summary = "B-scan RAW сохранён; декодер B-scan в этом UI не встроен"
            else:
                summary = "RAW сохранён; декодер для типа не задан"
        except Exception as exc:
            status = f"decode_error: {exc}"
            decoded = False

    if decoded:
        summary = summary_from_fields(addr, fields, params)
    if not summary:
        summary = "получено" if status.startswith("ok") else status
    return {
        "addr": addr,
        "base_kind": base_kind,
        "status": status,
        "decoded": decoded,
        "fields": fields,
        "params": params,
        "summary": summary,
    }


def _v25_apply_decoded_payload(self: NativeLikeBasketExactApp, raw_id: int, result: dict[str, Any], record: bytes) -> dict[str, Any]:
    """Apply a decoded worker result on the DB-owning collection thread."""
    addr = int(result.get("addr") or 0)
    base_kind = str(result.get("base_kind") or kind_for_addr(addr))
    status = str(result.get("status") or "")
    decoded = bool(result.get("decoded"))
    fields = dict(result.get("fields") or {})
    params = dict(result.get("params") or {})
    summary = str(result.get("summary") or "")

    if decoded:
        ver = _v25_payload_version_from_db(self.db, addr, fields.get("NUMVERS", ""))
        if ver:
            fields = dict(fields)
            fields["NUMVERS"] = ver
        if base_kind in ("report", "report_v2"):
            self.db.save_report(raw_id, addr, fields)
            try:
                _v14_patch_row_session_meta(self.db, "reports", addr)
            except Exception:
                pass
        elif base_kind in ("protocol_short", "protocol_graph"):
            self.db.save_protocol(raw_id, addr, fields)
            try:
                graph_addr = graph_addr_for_protocol(addr)
                graph_raw_row = self.db.get_raw_by_addr(graph_addr)
                setting_addr = protocol_setting_addr_643(record)
                setting_raw_row = self.db.get_raw_by_addr(setting_addr)
                diag = diagnose_protocol_643(
                    addr,
                    record,
                    bytes(graph_raw_row["raw"]) if graph_raw_row else None,
                    bytes(setting_raw_row["raw"]) if setting_raw_row else None,
                )
                self.db.save_protocol_diagnostic(diag)
            except Exception:
                pass
            try:
                _v14_patch_row_session_meta(self.db, "protocols", addr)
            except Exception:
                pass
        elif base_kind == "setting":
            self.db.save_setting(raw_id, addr, fields, params)
            try:
                _v14_patch_row_session_meta(self.db, "settings", addr)
            except Exception:
                pass
        try:
            _apply_operator_directory_to_addr(self.db, addr)
        except Exception:
            pass

    if not summary:
        summary = "получено" if status.startswith("ok") else status
    self._update_idx_after_fetch(addr, len(record), decoded, status, summary)
    return {"ok": status.startswith("ok"), "decoded": decoded, "status": status}


def _v25_worker_get_data_parallel(self: NativeLikeBasketExactApp) -> None:
    """Read serial records sequentially, decode records in parallel, refresh UI via queue.

    Pipeline stages:
      1. COM thread reads 55/42 frames in strict order (single owner of serial).
      2. A small CPU pool decrypts/decodes independent records concurrently.
      3. The collection thread applies DB writes in batches.
      4. Tk UI is refreshed only by the normal `uiq`/`after()` path.
    """
    import concurrent.futures

    overall_started = time.perf_counter()
    max_workers = max(2, min(4, (os.cpu_count() or 2)))
    pending: dict[Any, tuple[int, int, bytes, str]] = {}
    ok = 0
    decoded = 0

    def drain_completed(block: bool = False) -> None:
        nonlocal decoded
        if not pending:
            return
        if block:
            done_iter = list(pending.keys())
        else:
            done_iter = [f for f in list(pending.keys()) if f.done()]
        for fut in done_iter:
            addr, raw_id, record, read_status = pending.pop(fut)
            try:
                result = fut.result()
            except Exception as exc:
                result = {
                    "addr": addr,
                    "base_kind": kind_for_addr(addr),
                    "status": f"decode_error: {exc}",
                    "decoded": False,
                    "fields": {},
                    "params": {},
                    "summary": f"ошибка дешифровки: {exc}",
                }
            applied = _v25_apply_decoded_payload(self, raw_id, result, record)
            if applied.get("decoded"):
                decoded += 1

    try:
        ser = self.ensure_serial()
        self.uiq.put(("progress", "Опрос 55... прошло 0 с"))
        header = ser.handshake55(1)
        if len(header) < 0x12:
            raise RuntimeError(f"Прибор вернул слишком мало байт на 55: {len(header)}")
        ids = parse_header_addresses(header)
        self.header = header
        self.device_no = device_no_from_header(header)
        self.session_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._save_idx_list(ids, header)
        self.uiq.put(("reload", None))

        targets = [a for a in ids if self._wanted(a) and expected_len_for_addr(a) is not None]
        total = len(targets)
        if total == 0:
            self.uiq.put(("log", "В выбранном режиме нет адресов для запроса"))
            return

        read_started = time.perf_counter()
        expected_s = total / BENCHMARK_218_RECORDS_PER_SEC if BENCHMARK_218_RECORDS_PER_SEC > 0 else 0
        self.uiq.put((
            "progress",
            f"Найдено {total} записей. Потоки дешифровки: {max_workers}. Ожидаемое время чтения: ~{self._fmt_elapsed(expected_s)}",
        ))

        self.db.begin_bulk()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="peleng-decode") as pool:
                for i, addr in enumerate(targets, 1):
                    elapsed_read = time.perf_counter() - read_started
                    elapsed_total = time.perf_counter() - overall_started
                    rate = (i - 1) / elapsed_read if elapsed_read > 0 and i > 1 else 0.0
                    eta = (total - i + 1) / rate if rate > 0 else (total - i + 1) / BENCHMARK_218_RECORDS_PER_SEC
                    self.uiq.put((
                        "progress",
                        f"Чтение {i}/{total}: {addr}  | прошло {self._fmt_elapsed(elapsed_total)} | осталось ~{self._fmt_elapsed(eta)}",
                    ))

                    expected = expected_len_for_addr(addr) or 0
                    wire = ser.request42_raw(addr, expected)
                    record = normalize_record_response(wire, addr, expected)
                    status = self._record_status(addr, wire, record, expected)
                    base_kind = kind_for_addr(addr)
                    save_kind = base_kind if status.startswith("ok") else f"{base_kind}_incomplete"
                    raw_id = self.db.save_raw(addr, save_kind, record, self.device_no, self.header, event_raw=wire)
                    if status.startswith("ok"):
                        ok += 1

                    fut = pool.submit(
                        _v25_decode_record_payload,
                        {
                            "addr": addr,
                            "record": record,
                            "status": status,
                            "base_kind": base_kind,
                            "device_no": self.device_no,
                        },
                    )
                    pending[fut] = (addr, raw_id, record, status)
                    drain_completed(False)

                    if len(pending) >= max_workers * 3:
                        done, _not_done = concurrent.futures.wait(
                            pending.keys(),
                            return_when=concurrent.futures.FIRST_COMPLETED,
                        )
                        for fut_done in done:
                            if fut_done in pending:
                                addr0, raw_id0, record0, _status0 = pending.pop(fut_done)
                                try:
                                    result0 = fut_done.result()
                                except Exception as exc:
                                    result0 = {
                                        "addr": addr0,
                                        "base_kind": kind_for_addr(addr0),
                                        "status": f"decode_error: {exc}",
                                        "decoded": False,
                                        "fields": {},
                                        "params": {},
                                        "summary": f"ошибка дешифровки: {exc}",
                                    }
                                applied0 = _v25_apply_decoded_payload(self, raw_id0, result0, record0)
                                if applied0.get("decoded"):
                                    decoded += 1

                    if i % UI_RELOAD_EVERY == 0 or i == total:
                        drain_completed(False)
                        self.db.end_bulk()
                        self.db.begin_bulk()
                        self.uiq.put(("reload", None))

                drain_completed(True)
        finally:
            self.db.end_bulk()

        read_elapsed = time.perf_counter() - read_started
        total_elapsed = time.perf_counter() - overall_started
        speed = total / read_elapsed if read_elapsed > 0 else 0.0
        self.uiq.put(("reload", None))
        self.uiq.put((
            "log",
            f"Готово за {self._fmt_elapsed(total_elapsed)}: запрошено {total}, получено {ok}, "
            f"дешифровано {decoded}, скорость чтения {speed:.2f} зап/с, потоков дешифровки {max_workers}",
        ))
        archive_path = _v25_archive_runtime_raw(self, "bulk")
        if archive_path:
            self.uiq.put(("log", f""))
    except Exception as exc:
        self.uiq.put(("error", str(exc)))
    finally:
        self.uiq.put(("busy", False))


def main() -> None:  # type: ignore[override]
    install_latest_v25_overrides()
    app = NativeLikeBasketExactApp()
    _v25_install_runtime_indexes(app.db)
    restored = _v25_restore_idx_catalog_from_raw(app.db)
    if restored:
        try:
            app.reload_idx_tables()
            app.status_var.set(f"Восстановлено из SQLite: {restored} записей")
        except Exception:
            pass
    app.mainloop()


if __name__ == "__main__":
    main()
