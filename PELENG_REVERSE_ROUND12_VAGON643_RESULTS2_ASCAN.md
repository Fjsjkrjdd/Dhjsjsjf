# PELENG REVERSE — Round 12 / ВАГОННАЯ 6.43: RESULTS2, A-развёртка, NASTR2 и GUI-декодер

> Продолжение предыдущих markdown-раундов по PelengPC / `102_203dll.dll` / `zapis2.exe`.
>
> Фокус этого раунда:
>
> - версия прибора: **ВАГОННАЯ 6.43**;
> - таблицы: **RESULTS2**, **NASTR2**, **SHORTPROT2**;
> - протоколы A-развёртки: диапазоны **4000..4999** и **6000..6999**;
> - отчёты контроля: диапазон **10000..19999**;
> - связь **протокол → настройка**;
> - построение графика A-развёртки;
> - offsets для зон **ВС1/ВС2**;
> - новая Python GUI-реализация с SQLite.

---

## 0. Цель раунда

Пользователь указал реальную версию дефектоскопа:

```text
ВАГОННАЯ 6.43
```

Основная задача была расширена:

1. Сначала — `SHORTPROT2` / «Отчёт о контроле» `idx 10..19`.
2. Затем — **RESULTS2**, то есть протокол A-развёртки.
3. Затем — связать `RESULTS2` с настройками `NASTR2`.
4. Затем — найти график A-развёртки и зоны `ВС1/ВС2`.
5. Затем — собрать всё в самостоятельный GUI-клон на Python + SQLite.

---

## 1. Адресные диапазоны и размеры записей для ВАГОННОЙ 6.43

В `PelengPC.exe` подтверждена таблица типов записей, где каждому диапазону адресов соответствует фиксированный размер записи.

| Диапазон адресов | Размер записи | Таблица/смысл |
|---:|---:|---|
| `1000..1999` | `0x0176` / 374 байта | `NASTR2` — настройки |
| `4000..4999` | `0x02B6` / 694 байта | `RESULTS2` — A-развёртка, краткая/табличная запись |
| `5000..5999` | `0x0FD6` / 4054 байта | `RESULTS2` — B-развёртка |
| `6000..6999` | `0x03A6` / 934 байта | `RESULTS2` — A-развёртка, расширенная запись с графиком |
| `10000..19999` | `0x0056` / 86 байт | `SHORTPROT2` — отчёты контроля |
| `20000..29999` | `0x0056` / 86 байт | отчёты V2 / другой report branch |

Практическая модель чтения:

```text
0x55
  → получить список/заголовок/адреса

0x42 + AddrLE16
  → получить payload фиксированного размера,
     где размер зависит от диапазона addr
```

---

## 2. Важное различие: record, body и zapis2-base

В этом раунде несколько раз уточнялся сдвиг. Итоговая модель:

### 2.1 Чистый payload от `0x42`

В Python GUI под `record` понимается **чистая запись**, полученная по `0x42 + addr`.

```text
record[0x00..] = payload ответа 0x42
```

### 2.2 DLL body

Для DLL/writer-функций `body` начинается внутри записи:

```text
body = record + 0x10
```

Например, если старые markdown говорят:

```text
TYPEVAR = body + 0x5E
```

то для чистого `record` это:

```text
TYPEVAR = record + 0x6E
```

### 2.3 `zapis2.exe` base

`zapis2.exe` получает не голый `record`, а буфер с 16-байтной служебной шапкой:

```text
zapis_base + 0x00..0x0F = служебная шапка EXE/viewer
zapis_base + 0x10       = чистый record от 0x42
```

Поэтому для offsets, найденных в таблицах `zapis2.exe`, используется перевод:

```text
record_offset = zapis2_offset - 0x10
```

Это критическое исправление. Ранее рассматривался вариант `-0x20`, но он был отвергнут после сверки полей `NUMOBJ` и других смещений.

---

## 3. RESULTS2 / A-развёртка 6.43 — табличные поля

Для ВАГОННОЙ 6.43 A-протоколы находятся в диапазонах:

```text
4000..4999
6000..6999
```

Для отображения списка протоколов используются поля `RESULTS2`.

### 3.1 Поля RESULTS2 для A-scan 6.43

| Поле | Источник | Decode |
|---|---:|---|
| `NUMBER` | не из прибора | `"0"` |
| `TYPEZAP` | decoder | `"Протокол А-развертки"` |
| `NUMKOD` | `addr` | `addr % 1000` |
| `DATEFORM` | `body+0x07..0x09` | `DD.MM.YYYY` |
| `TIMEFORM` | `body+0x0A..0x0B` | `HH:MM` |
| `KODOPERA` | служебное поле record/viewer | `LE16` |
| `NAMEOPERA` | не из прибора | `" "` |
| `NUMVERS` | record/header | `"6.43"` |
| `NUMPRIB` | header/контекст прибора | номер прибора |
| `TYPEVAR` | `body+0x5E..0x5F` | `LE16`, типовой вариант |
| `NUMOBJ` | `body+0x11`, len `0x0B` | `PassportLUT` |
| `SMELTING` | `body+0x35`, len `0x07` | `PassportLUT` |
| `INDMAKER` | `body+0x3C..0x3D` | `LE16` |
| `MAKETIME` | `body+0x3E..0x3F` | `LE16` |
| `DEFEKT` | `body+0x0C` | `"есть"` если != 0, иначе `"нет"` |
| `CODEDEF` | `body+0x21`, len `0x07` | `PassportLUT` |
| `NUMZAP` | БД | ID записи/строки |

### 3.2 Поля, которые НЕ используются в вагонной ветке

В ранних схемах встречались поля:

```text
KM
M
MM
STAGE
SECTION
PICKETLINE
PATH
PLACE
```

Для **ВАГОННОЙ 6.43** в нашем A-протоколе эти поля не используются как основная схема. Они относятся к другой ветке/другой схеме, вероятно рельсовой/путевой.

---

## 4. Связь протокол → настройка

Найдена и исправлена связь `RESULTS2 → NASTR2`.

### 4.1 Неверная ранняя гипотеза

Ранее рассматривалось:

```python
setting_no = LE16(body + 0x5E)
```

Это неверно для связи протокол→настройка, потому что `body+0x5E` — это `TYPEVAR`, типовой вариант.

### 4.2 Правильная связь

В таблицах `zapis2.exe` поле **«Номер настройки»** находится по offset:

```text
zapis2 offset 0x2D
```

С учётом `record_offset = zapis2_offset - 0x10`:

```text
record offset 0x1D
```

Итоговая формула:

```python
setting_no = LE16(record + 0x1D)
setting_addr = 1000 + setting_no
```

Готовые функции:

```python
def le16(buf: bytes, off: int) -> int:
    return buf[off] | (buf[off + 1] << 8)

def protocol_setting_no_643(record: bytes) -> int:
    return le16(record, 0x1D)

def protocol_setting_addr_643(record: bytes) -> int:
    return 1000 + protocol_setting_no_643(record)
```

### 4.3 Важный практический вывод

Для построения A-протокола:

```text
протокол 4000+n / 6000+n
  → setting_no = LE16(record+0x1D)
  → настройка = 1000 + setting_no
```

В GUI настройку нужно подтягивать лениво:

```text
если setting_addr ещё нет в SQLite:
    выполнить 0x42 + setting_addr
    сохранить NASTR2 raw
    декодировать NASTR2
```

---

## 5. График A-развёртки

График найден в `zapis2.exe`, а не в `PelengPC.exe` renderer-цепочке.

### 5.1 Таблица `zapis2.exe`

Для ВАГОННОЙ 6.42/6.43 и type-code:

```text
0x2A06
0x2B06
```

используются таблицы:

```text
0x4D99C0
0x4DE368
0x4DB028
```

Для графика у них общий header/offset:

```text
zapis2 graph offset = 0x1E5
```

С учётом `record_offset = zapis2_offset - 0x10`:

```text
record graph offset = 0x1D5
```

### 5.2 Копирование графика в `zapis2.exe`

В `zapis2.exe` подтверждён код:

```text
src = raw_blob + 0x1E5
len = 0xF4
memcpy(dst, src, len)
```

Для Python/чистого record:

```text
src = record + 0x1D5
len = 0xF4
```

### 5.3 Почему полный график берётся из 6000+n

Для записи `4000+n`:

```text
record_len = 0x02B6
graph_end = 0x1D5 + 0xF4 = 0x2C9
0x2C9 > 0x2B6
```

Полный графический блок не помещается в короткую запись `4000+n`.

Для записи `6000+n`:

```text
record_len = 0x03A6
graph_end = 0x2C9
0x2C9 < 0x3A6
```

Итог:

```text
4000+n = краткая/табличная A-запись
6000+n = расширенная A-запись с полным графиком
```

Практическая функция:

```python
def graph_addr_for_protocol(addr: int) -> int:
    if 6000 <= addr <= 6999:
        return addr
    if 4000 <= addr <= 4999:
        return 6000 + (addr - 4000)
    raise ValueError(f"not A-scan protocol addr: {addr}")
```

### 5.4 Финальная формула графика

```python
GRAPH_OFF = 0x1D5
GRAPH_COPY_LEN = 0xF4
GRAPH_DRAW_COUNT = 0xF3
GRAPH_BASELINE = 0x8C

def decode_ascan_graph_643(record: bytes) -> dict:
    need = GRAPH_OFF + GRAPH_COPY_LEN
    if len(record) < need:
        raise ValueError(
            f"record too short for A-scan graph: len=0x{len(record):X}, need=0x{need:X}"
        )

    copied = list(record[GRAPH_OFF:need])
    samples = copied[:GRAPH_DRAW_COUNT]

    return {
        "offset": GRAPH_OFF,
        "copy_len": GRAPH_COPY_LEN,
        "draw_count": GRAPH_DRAW_COUNT,
        "baseline": GRAPH_BASELINE,
        "samples_u8": samples,
        "amplitudes": [s - GRAPH_BASELINE for s in samples],
        "min_sample": min(samples),
        "max_sample": max(samples),
        "line_mode": (record[0x128] & 1) == 0,
    }
```

### 5.5 Масштаб графика

В `zapis2.exe` renderer использует:

```text
width    = 0x118 = 280 px
height   = 0x0C8 = 200 px
baseline = 0x8C  = 140
```

Практически для GUI:

```python
amplitude = sample - 0x8C
```

---

## 6. Зоны ВС1 / ВС2 / дополнительный интервал

### 6.1 Финальные offsets для чистого record

| Поле | Record offset | Decode |
|---|---:|---|
| Номер настройки | `0x1D` | `LE16` |
| Флаг line/fill | `0x128` | `record[0x128] & 1` |
| ВС1 threshold | `0xC7` | `u8` |
| ВС1 method | `0xC8` | `u8 enum` |
| ВС1 start | `0xCD` | `LE16` |
| ВС1 end | `0xCF` | `LE16` |
| ВС2 threshold | `0xD1` | `u8` |
| ВС2 method | `0xD2` | `u8 enum` |
| ВС2 start | `0xD7` | `LE16` |
| ВС2 end | `0xD9` | `LE16` |
| Extra/ВРЧ start | `0xDF` | `LE16` |
| Extra/ВРЧ end | `0xE1` | `LE16` |

### 6.2 Enum методов

```python
VS1_METHODS = {
    0: "эхо",
    1: "ЗТМ",
    2: "теневой",
    3: "зеркальный",
    4: "2 эхо",
}

VS2_METHODS = {
    0: "эхо",
    1: "зтм",
    2: "нет",
}
```

### 6.3 Координаты X

Для основной ветки координаты зон уже лежат в координатах графика/сэмплов. Не надо делить их на длительность развёртки.

```python
ASCAN_WIDTH = 0x118      # 280 px
ASCAN_POINT_COUNT = 0xF4 # 244 copied points

def graph_x_from_raw(raw_x: int) -> int:
    return round(raw_x * ASCAN_WIDTH / ASCAN_POINT_COUNT)
```

### 6.4 Декодер зон

```python
def decode_ascan_zones_643(record: bytes) -> dict:
    vs1_start = le16(record, 0xCD)
    vs1_end = le16(record, 0xCF)
    vs2_start = le16(record, 0xD7)
    vs2_end = le16(record, 0xD9)
    extra_start = le16(record, 0xDF)
    extra_end = le16(record, 0xE1)

    return {
        "setting_no": protocol_setting_no_643(record),

        "vs1_threshold": record[0xC7],
        "vs1_method_raw": record[0xC8],
        "vs1_method": VS1_METHODS.get(record[0xC8], f"unknown({record[0xC8]})"),
        "vs1_start_raw": vs1_start,
        "vs1_end_raw": vs1_end,
        "vs1_start_px": graph_x_from_raw(vs1_start),
        "vs1_end_px": graph_x_from_raw(vs1_end),

        "vs2_threshold": record[0xD1],
        "vs2_method_raw": record[0xD2],
        "vs2_method": VS2_METHODS.get(record[0xD2], f"unknown({record[0xD2]})"),
        "vs2_start_raw": vs2_start,
        "vs2_end_raw": vs2_end,
        "vs2_start_px": graph_x_from_raw(vs2_start),
        "vs2_end_px": graph_x_from_raw(vs2_end),

        "extra_start_raw": extra_start,
        "extra_end_raw": extra_end,
        "extra_start_px": graph_x_from_raw(extra_start),
        "extra_end_px": graph_x_from_raw(extra_end),
    }
```

---

## 7. Спецрежим `0x405C4C`

### 7.1 Что выяснено

`0x405C4C` не является обязательным renderer’ом для обычного A-протокола. Он вызывается только если:

```text
control_table != 0
read_u8(raw + control_table[0]) == 3
```

Для вагонных таблиц control-table:

```text
0x4D9308
```

Её первый элемент:

```text
control_table[0] = 0x100
```

С учётом `record_offset = zapis2_offset - 0x10`:

```text
record offset = 0xF0
```

Практическая проверка:

```python
def uses_special_geometry_643(record: bytes) -> bool:
    return len(record) > 0xF0 and record[0xF0] == 3
```

### 7.2 Важный вывод

Для таблицы `0x4D9308` поле `control_table+0x40` равно `0`.

Внутри `0x405C4C` есть вызов через:

```text
call [control_table + 0x40]
```

Если бы `record[0xF0] == 3`, оригинал мог бы уйти в null-call. Поэтому для валидных данных ВАГОННОЙ 6.43 это состояние, вероятно, не ожидается.

Практическое поведение GUI:

```text
если record[0xF0] == 3:
    показать предупреждение:
    "Спецгеометрия 0x405C4C / режим 3 обнаружен, не поддержан"
иначе:
    использовать обычный renderer 0x405236 + зоны
```

---

## 8. NASTR2 6.43 — offsets настройки

Таблица `NASTR2` 6.42/6.43 содержит 38 параметров. Ниже offsets уже пересчитаны для чистого `record` от `0x42 addr=1000+n`.

| Поле | Record offset | Decode |
|---|---:|---|
| Номер настройки | `0x1D` | `LE16` |
| Шифр оператора | `0x65` | `LE16` |
| Типовой вариант | `0x6E` | `LE16` |
| Частота УЗК | `0x84` | `u8/raw` |
| Скорость УЗК | `0x88` | `LE16` |
| № ПЭП | `0x7C` | `u8` |
| вкл. ПЭП | `0x7B` | `u8` |
| Угол ввода | `0x8A` | `LE16` |
| Время в ПЭП | `0x72` | `LE16` |
| Толщина | `0x9F` | `LE16` |
| Усиление | `0xA8` | `LE16` |
| Треб. чувств. | `0xA6` | `u8` |
| Факт. чувств. | `0xA7` | `u8` |
| Доп. усиление | `0xA5` | `u8` |
| Развёртка | `0xBF` | enum |
| Длительность | `0xC5` | `LE16` |
| W-развёртка | `0x70` | `u8` |
| Порог ВС1 | `0xC7` | `u8` |
| Метод ВС1 | `0xC8` | enum |
| Начало ВС1 | `0xC9` | `LE16` |
| Конец ВС1 | `0xCB` | `LE16` |
| Порог ВС2 | `0xD1` | `u8` |
| Метод ВС2 | `0xD2` | enum |
| Начало ВС2 | `0xD3` | `LE16` |
| Конец ВС2 | `0xD5` | `LE16` |
| Начало АРУ | `0xDB` | `LE16` |
| Конец АРУ | `0xDD` | `LE16` |
| Тип ВРЧ | `0xF0` | `u8` |
| Начало ВРЧ | `0xE4` | `LE16` |
| Конец ВРЧ | `0xE6` | `LE16` |
| Амплитуда ВРЧ | `0xED` | `u8` |
| Форма ВРЧ | `0xEC` | `u8` |
| До ВРЧ | `0xEE` | `u8` |
| После ВРЧ | `0xEF` | `u8` |

### 8.1 NASTR2 decoder

```python
def decode_nastr2_643(record: bytes) -> dict:
    vs1_method = record[0xC8]
    vs2_method = record[0xD2]

    return {
        "setting_no": le16(record, 0x1D),
        "operator_code": le16(record, 0x65),
        "typevar": le16(record, 0x6E),

        "freq_mhz_raw": record[0x84],
        "sound_speed": le16(record, 0x88),
        "probe_no": record[0x7C],
        "probe_enabled": record[0x7B],
        "angle_deg": le16(record, 0x8A),
        "probe_time_raw": le16(record, 0x72),
        "thickness_raw": le16(record, 0x9F),

        "gain_raw": le16(record, 0xA8),
        "required_sens_raw": record[0xA6],
        "actual_sens_raw": record[0xA7],
        "extra_gain_raw": record[0xA5],

        "sweep_type_raw": record[0xBF],
        "sweep_duration_raw": le16(record, 0xC5),
        "w_sweep_enabled": record[0x70],

        "vs1_threshold_pct": record[0xC7],
        "vs1_method_raw": vs1_method,
        "vs1_method": VS1_METHODS.get(vs1_method, f"unknown({vs1_method})"),
        "vs1_start_raw": le16(record, 0xC9),
        "vs1_end_raw": le16(record, 0xCB),

        "vs2_threshold_pct": record[0xD1],
        "vs2_method_raw": vs2_method,
        "vs2_method": VS2_METHODS.get(vs2_method, f"unknown({vs2_method})"),
        "vs2_start_raw": le16(record, 0xD3),
        "vs2_end_raw": le16(record, 0xD5),

        "aru_start_raw": le16(record, 0xDB),
        "aru_end_raw": le16(record, 0xDD),

        "vrch_type_raw": record[0xF0],
        "vrch_start_raw": le16(record, 0xE4),
        "vrch_end_raw": le16(record, 0xE6),
        "vrch_amp_db_raw": record[0xED],
        "vrch_shape_raw": record[0xEC],
        "before_vrch_db_raw": record[0xEE],
        "after_vrch_db_raw": record[0xEF],
    }
```

---

## 9. SHORTPROT2 / отчёты контроля 10..19

Для отчётов контроля ВАГОННОЙ 6.43 путь:

```text
idx 10..19
→ DecodeReportV1
→ SchemaRouter sweep_id=643
→ writer 0x4041d0
→ SHORTPROT2
```

Поля:

| Поле | Decode |
|---|---|
| `NUMBER` | `"0"` |
| `NUMKOD` | `sweep_addr % 10000` |
| `DATEFORM` | дата |
| `TIMEFORM` | время |
| `KODOPERA` | `LE16` |
| `NAMEOPERA` | `" "` |
| `NUMVERS` | `"6.43"` |
| `NUMPRIB` | номер прибора |
| `TYPEVAR` | `LE16` |
| `NUMOBJ` | `PassportLUT` |
| `CODEDEF` | `u8`, для SHORTPROT2 это **Количество дефектов** |
| `PROTOCOL` | `PassportLUT` |
| `NUMZAP` | БД |

Важное: в `SHORTPROT2` поле `CODEDEF` означает **количество дефектов**, а не строковый код дефекта.

---

## 10. SQLite/GUI модель

Создан новый GUI-скрипт:

```text
peleng_vagon643_full_gui.py
```

### 10.1 Функции GUI

- Открывает COM-порт.
- Шлёт `0x55`, получает заголовок/список адресов.
- По найденным адресам шлёт `0x42 + AddrLE16`.
- Сортирует записи по вкладкам:
  - `Настройки`
  - `Протоколы A-развёртки`
  - `Отчёты контроля`
- Сохраняет raw BLOB в SQLite.
- Сохраняет расшифрованные поля в SQLite.
- По двойному клику:
  - протокол → полная дешифровка + график + зоны + настройка;
  - настройка → полная дешифровка NASTR2;
  - отчёт → полная дешифровка SHORTPROT2.

### 10.2 Главные правила GUI

```text
Если открыт протокол 4000+n:
    табличные поля берутся из 4000+n
    график берётся из 6000+n

Если открыт протокол 6000+n:
    табличные поля и график можно брать из 6000+n

Настройка:
    setting_no = LE16(protocol_record+0x1D)
    setting_addr = 1000 + setting_no
```

### 10.3 SQLite таблицы

В GUI используются таблицы:

```text
raw_records
protocols
settings
reports
protocol_setting_link
```

Смысл:

- `raw_records` — хранит все сырые payload’ы от прибора.
- `protocols` — decoded RESULTS2.
- `settings` — decoded NASTR2.
- `reports` — decoded SHORTPROT2.
- `protocol_setting_link` — связь `protocol_addr → setting_addr`.

---

## 11. Что теперь считается 1:1 для ВАГОННОЙ 6.43

Считаем закрытым для обычной ветки:

```text
1. Чтение записей по 0x42.
2. Размеры NASTR2 / RESULTS2 / SHORTPROT2.
3. Сортировка адресов по вкладкам.
4. Связь протокол→настройка через record+0x1D.
5. График A-развёртки через record6000[0x1D5 : 0x1D5+0xF4].
6. Baseline 0x8C.
7. Draw count 0xF3.
8. ВС1/ВС2 offsets.
9. NASTR2 offsets.
10. SHORTPROT2 fields.
```

Остаётся диагностически:

```text
1. Спецрежим record[0xF0] == 3 / 0x405C4C.
2. Полная физическая интерпретация Real48-полей.
3. Словари TYPEVAR / INDMAKER / CODEDEF можно расширять из zapis2.exe.
4. Проверить всё на живом дампе прибора.
```

---

## 12. Практический чек-лист для теста на приборе

1. Запустить GUI.
2. Нажать «Получить».
3. Убедиться, что появились:
   - настройки `1000+n`;
   - протоколы `4000+n`;
   - протоколы `6000+n`;
   - отчёты `10000+n`.
4. Открыть протокол `4000+n`.
5. Проверить:
   - подтянулся `6000+n`;
   - подтянулась настройка `1000+setting_no`;
   - график построился;
   - зоны ВС1/ВС2 отображаются;
   - `setting_no` совпадает с тем, что видно на приборе.
6. Если график пустой/странный:
   - проверить наличие `6000+n`;
   - проверить длину `record >= 0x2C9`;
   - сохранить raw для ручной сверки.
7. Если `record[0xF0] == 3`:
   - записать как спецрежим;
   - текущий GUI должен показать предупреждение.

---

## 13. Минимальные константы для реализации

```python
# relation
SETTING_NO_OFF = 0x1D

# graph
GRAPH_OFF = 0x1D5
GRAPH_COPY_LEN = 0xF4
GRAPH_DRAW_COUNT = 0xF3
GRAPH_BASELINE = 0x8C
LINE_FLAG_OFF = 0x128

# zones
VS1_THRESHOLD_OFF = 0xC7
VS1_METHOD_OFF = 0xC8
VS1_START_OFF = 0xCD
VS1_END_OFF = 0xCF

VS2_THRESHOLD_OFF = 0xD1
VS2_METHOD_OFF = 0xD2
VS2_START_OFF = 0xD7
VS2_END_OFF = 0xD9

EXTRA_START_OFF = 0xDF
EXTRA_END_OFF = 0xE1

# record sizes
NASTR2_LEN = 0x0176
ASCAN_4000_LEN = 0x02B6
ASCAN_6000_LEN = 0x03A6
BSCAN_LEN = 0x0FD6
SHORTPROT2_LEN = 0x0056
```

---

## 14. Короткий итог раунда

Главные новые находки:

```text
1. ВАГОННАЯ 6.43 A-протокол разделён на 4000+n и 6000+n.
2. Полный график находится в 6000+n.
3. График: record+0x1D5, len 0xF4, draw 0xF3, baseline 0x8C.
4. Связь с настройкой: setting_no = LE16(record+0x1D).
5. Настройка читается по адресу 1000+setting_no.
6. ВС1/ВС2 offsets найдены и пересчитаны для чистого record.
7. NASTR2 offsets найдены и пересчитаны для чистого record.
8. Для обычной ветки 6.43 `0x405C4C` не обязателен.
9. GUI собран в Python + tkinter + sqlite3 + pyserial.
```
