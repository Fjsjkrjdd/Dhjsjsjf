# PELENG REVERSE — Round 13 / Python GUI v32→v34: live RAW, exact-55, offsets, декодеры

> Продолжение заметок по PelengPC / `102_203dll.dll` / `zapis2.exe`.
>
> Скоуп этого файла: статический разбор трёх Python-скриптов GUI/SQLite:
>
> - `peleng_vagon643_full_gui_v32_round44_session_raw_header55_fix.py`
> - `peleng_vagon643_full_gui_v33_round45_script_raw_wire_fix.py`
> - `peleng_vagon643_full_gui_v34_round46_exact55_clean_logic.py`
>
> Скрипты не запускались на приборе. Анализ ниже — только по Python-коду и его внутренним комментариям.

---

## 0. Главный итог

Для дальнейшей работы основной вариант — **v34 / round46 exact55 clean logic**.

Он отличается от предыдущих веток тем, что старается максимально убрать синтетику:

```text
0x55:
  читать один раз;
  воспринимать ответ как header16 + flat WORD Idx list;
  сохранять порядок Idx как пришёл от прибора;
  не сортировать;
  не дедуплицировать;
  не расширять контейнеры отчётов;
  не добавлять native_slots;
  не brute-force настройки.

0x42:
  отправлять ровно 42 LL HH;
  читать один раз до expected_len по таблице диапазонов;
  retry = off;
  пустые/короткие/битые ответы сохранять как raw diagnostics.
```

Скрипт v33 важен как промежуточный фикс **wire RAW vs normalized RAW**: `raw_events` должны хранить точный проводной ответ, а декодеры должны получать нормализованный `record`.

Скрипт v34 поверх v33 делает **clean logic**: не трогает DTR/RTS, возвращает `wait(10)` как 10 мс, убирает искусственный `command_cooldown`, принимает `FF FF` и `FD FF` как хвост `0x55`.

---

## 1. Входные файлы и роль версий

| Файл | Роль |
|---|---|
| `v32_round44_session_raw_header55_fix.py` | База exact-55/session RAW. Уже содержит строгую модель `0x55`/`0x42`, но ещё не отделяет wire RAW от normalized record так аккуратно, как v33. |
| `v33_round45_script_raw_wire_fix.py` | Важный фикс сохранения сырых ответов: `request42_raw()` + `fetch_record_pair()` + `save_raw(..., event_raw=...)`. Также пробовал явно включать DTR/RTS. |
| `v34_round46_exact55_clean_logic.py` | Текущий канон. Убирает лишнее управление DTR/RTS, возвращает 10 ms gap, `command_cooldown=0`, включает `20xxx..29xxx` из exact-55, если прибор сам их объявил. |

---

## 2. Транспорт COM / протокол обмена

### 2.1 Параметры линии в текущем скрипте

В v34 фактические default-константы:

```python
DEFAULT_BAUD = 19200
DEFAULT_BYTESIZE = 8
DEFAULT_PARITY = "N"
DEFAULT_STOPBITS = 1
DEFAULT_INTER_BYTE_GAP = 0.010
DEFAULT_COMMAND_COOLDOWN = 0.000
```

Важно: в комментариях ещё остался reverse-след про `19200 8E1`, но текущая clean-ветка использует **8N1**. Комментарий `parse_header_addresses()` прямо фиксирует round43: live serial line должен оставаться `19200 8N1`, потому что ранняя EVEN parity интерпретация делала `55` Idx нечитаемым/пустым.

Итог для практики:

```text
текущий live-профиль Python v34 = 19200 8N1
```

### 2.2 DTR/RTS

Эволюция:

```text
v32:
  принудительно DTR=False, RTS=False

v33:
  Round45 — принудительно DTR=True, RTS=True,
  потому что некоторые USB-RS232/RS485 адаптеры завязаны на эти линии

v34:
  Round46 — не трогать DTR/RTS вообще;
  оставить состояние драйвера/pyserial по умолчанию
```

Каноническая логика v34:

```text
DTR/RTS = driver-default
```

Причина: и принудительное выключение, и принудительное включение — это дополнительное поведение, которого в текущей реконструкции original exchange path нет.

### 2.3 Команда `0x55`

`handshake55()`:

```python
self.ser.reset_input_buffer()
self.ser.write(b"\x55")
self.ser.flush()
return self.read_until_ff_ff(...)
```

Правила:

```text
1. Отправляется ровно один байт 0x55.
2. Параметр hs_count фактически игнорируется.
3. Несколько 0x55 подряд считаются вредными:
   они склеивают ответы и ломают fixed offset-0x10 ID list.
4. Чтение идёт до FF FF.
5. Если FF FF не пришёл, допускается quiet-line fallback после начала данных.
```

### 2.4 Парсинг ответа `0x55`

Текущая модель live COM:

```text
response[0x00..0x0F] = service header
response[0x10..]     = flat WORD Idx payload
words_total          = (len(response) - 0x10) // 2
words_used           = words_total - 1
```

Ключевое исправление:

```text
live 55 ≠ PLG block stream
live 55 = flat little-endian WORD list
```

В v34 хвостовыми маркерами считаются оба варианта:

```text
FF FF
FD FF
```

Практическое правило:

```python
if v in (0xFFFF, 0xFFFD):
    stop_found = True
    break
```

### 2.5 План чтения `0x42`

В v34 `build_address_plan()` строится только из реально пришедшего `0x55` Idx:

```text
sort=off
dedup=off
brute=off
native_slots=off
report_expand=off
byte_recovery=off
retry=off
```

Фильтры остаются только два:

```text
1. GUI checkbox категории: settings / protocols / reports
2. expected_len_for_addr(addr) должен знать длину диапазона
```

Адреса `20xxx..29xxx` в v34 снова не отбрасываются заранее:

```text
если прибор сам объявил 20xxx ID в 55
и таблица expected_len говорит 0x56,
то адрес один раз читается и сохраняется raw
```

Это отличается от v33, где UI-ветка отчётов была ограничена `10000..19999`.

### 2.6 Команда `0x42`

Текущий путь:

```text
send:
  0x42
  low(addr)
  high(addr)

gap:
  10 ms между байтами в v34
```

Важное поведение:

```text
- input buffer НЕ чистится перед каждым 0x42;
- это сделано, чтобы не выбросить поздний checksum/tail byte;
- retry на тот же адрес не делается;
- если ответ короткий/битый, он сохраняется как diagnostic raw.
```

### 2.7 Модель приёма `0x42`

`read_frame_len_2_3()` моделирует исправленную OnRxChar-логику:

```text
PelengPC.exe 0x411810 = OnRxChar event handler,
а не polling loop на 8 ms.
```

Правила:

```text
1. Ждём первый байт.
2. Если первые два байта = FD FF или FF FF → это полный empty marker.
3. Далее читаем chunks до 0x400 байт, как original ReadFile path.
4. Цель чтения — expected_len_for_addr(addr), а не rx[2:4].
5. Если не хватает хвоста, ждём поздний хвост в том же запросе.
6. Новый 0x42 не отправляем.
7. Если всё равно short — сохраняем как diagnostic raw.
```

---

## 3. Таблица длин `expected_len_for_addr`

Текущий Python-декодер использует прямую таблицу диапазонов:

| Диапазон | len | kind |
|---:|---:|---|
| `1000..1999` | `0x0176` | `setting` / `NASTR2` |
| `4000..4999` | `0x02B6` | `protocol_short` / `RESULTS2 A-scan` |
| `5000..5999` | `0x0FD6` | `bscan` |
| `6000..6999` | `0x03A6` | `protocol_graph` / extended A-scan |
| `10000..19999` | `0x0056` | `report` / `SHORTPROT2` |
| `20000..29999` | `0x0056` | `report_v2` / report-like raw |

Ключевой комментарий в коде:

```text
PelengPC.exe использует таблицу длин по ID, а не rx[2:4].
```

Для `6000..6999` особенно важно:

```text
внутренний заголовок может объявлять 0x56,
но это не длина всей записи с графиком;
останавливаться на 0x56 нельзя.
```

---

## 4. `record`, wire RAW и normalized RAW

### 4.1 v33/v34 фикс

До v33 `request42()` мог нормализовать ответ до того, как байты попадали в `raw_events`. Из-за этого RAW ZIP терял настоящий wire response.

Исправление v33:

```python
wire = ps.request42_raw(addr, expected)
raw  = normalize_record_response(wire, addr, expected)
save_raw(..., raw=raw, event_raw=wire)
```

Разделение:

| Сущность | Смысл |
|---|---|
| `wire_raw` / `raw_events.raw` | точный ответ с линии, как пришёл |
| `normalized_record` / `raw_records.raw` | очищенный payload для декодеров |
| `raw_records` | latest visible table, адрес уникален |
| `raw_events` | append-only trace всех попыток/ответов |

### 4.2 Нормализация ответа

`normalize_record_response()` умеет:

```text
1. Если resp начинается с addr и len >= expected:
   record = resp[0:expected]

2. Если в resp есть внешняя 16-byte шапка:
   record = resp[0x10:0x10+expected]

3. Если addr найден в первых 0x40 байтах:
   record = resp[off:off+expected]

4. Если resp короче expected:
   вернуть как есть, чтобы сохранить forensic raw.
```

---

## 5. Важная поправка к Round12: live offsets отличаются от статической схемы

В шапке docstring v34 ещё остались старые Round12-константы:

```text
protocol→setting = record+0x1D
graph            = record+0x1D5
ВС1/ВС2          = 0xC7/0xC8...
```

Но фактический код v34 использует live-исправления:

```python
SETTING_NO_OFF = 0x0D
GRAPH_OFF = 0x1B8
VS1_THRESHOLD_OFF = 0xB3
VS1_METHOD_OFF    = 0xB4
VS1_START_OFF     = 0xB5
VS1_END_OFF       = 0xB7
VS2_THRESHOLD_OFF = 0xBC
VS2_METHOD_OFF    = 0xBD
VS2_START_OFF     = 0xBE
VS2_END_OFF       = 0xC0
EXTRA_START_OFF   = 0xCF
EXTRA_END_OFF     = 0xD1
```

Итог:

```text
Round12 offsets = статическая/zapis2-модель для чистого record
v34 offsets     = live RAW / current GUI-декодер для реальных дампов
```

Для дальнейшего реверса нужно всегда уточнять, о какой базе идёт речь:

```text
статическая база / zapis2-base / DLL body / live normalized record
```

---

## 6. A-протокол RESULTS2

### 6.1 Связь протокол → настройка

В v34 связь стала не одним offset, а устойчивой функцией с fallback:

```python
def protocol_setting_no_643(record):
    if 6000 <= raw_addr <= 6999 and len(record) < 0x60:
        пробовать 0x0C, 0x0E, 0x10, 0x0D
    иначе:
        пробовать 0x0D, 0x0C, 0x1C, 0x1D
```

Причина:

```text
- long 4000+n records: setting_no обычно живёт около 0x0D;
- short 6000+n fragments в BNEW могут хранить первый small LE16 на 0x0C;
- использование только 0x0D давало мусор вроде 512/2816;
- старые гипотезы 0x1C/0x1D оставлены как fallback.
```

Практическая формула v34:

```python
setting_no = protocol_setting_no_643(record)
setting_addr = 1000 + setting_no
```

### 6.2 Адрес графика

`graph_addr_for_protocol(addr)` в v34 возвращает сам адрес:

```text
4000+n → 4000+n
6000+n → 6000+n
```

Комментарий в коде:

```text
zapis2.exe отправляет 6000..6999 в тот же RESULTS2/A-scan класс,
что и длинные 4000-record.
График должен строиться из самой считанной записи,
а не из искусственного 4000+n fallback.
```

Это исправляет более раннюю практическую модель, где для `4000+n` часто искался `6000+n`.

### 6.3 Поиск блока графика

Фиксированный `GRAPH_OFF = 0x1B8` оставлен, но v34 уже не доверяет одному offset.

`find_ascan_graph_offset_643()` строит кандидаты:

```text
1. len(record) - 0xF4          # live captures: graph as final tail
2. 0x1B8                       # old short-frame fallback
3. 0x1C5
4. 0x1E5
5. len(record) - 0x100 - 0xF4
```

Затем выбирает лучший блок по `_score_graph_block()`:

```text
- блок должен быть 0xF4 байт;
- первые 0xF3 — samples;
- реальные samples имеют вариативность;
- много 00/FF штрафуется;
- значения около baseline 0x8C повышают score.
```

Декод графика:

```text
copy_len   = 0xF4
draw_count = 0xF3
baseline   = 0x8C
amplitude  = sample - 0x8C
line_mode  = (record[0x128] & 1) == 0
special_geometry = record[0xF0] == 3
```

### 6.4 Зоны ВС1/ВС2/ВРЧ в live graph-record

Текущие offsets v34:

| Поле | Offset |
|---|---:|
| `SETTING_NO_OFF` | `0x0D` |
| `VS1_THRESHOLD_OFF` | `0xB3` |
| `VS1_METHOD_OFF` | `0xB4` |
| `VS1_START_OFF` | `0xB5` |
| `VS1_END_OFF` | `0xB7` |
| `VS2_THRESHOLD_OFF` | `0xBC` |
| `VS2_METHOD_OFF` | `0xBD` |
| `VS2_START_OFF` | `0xBE` |
| `VS2_END_OFF` | `0xC0` |
| `EXTRA_START_OFF` | `0xCF` |
| `EXTRA_END_OFF` | `0xD1` |

Методы:

```python
VS1_METHODS = {
  0: "эхо",
  1: "ЗТМ",
  2: "теневой",
  3: "зеркальный",
  4: "2 эхо"
}

VS2_METHODS = {
  0: "эхо",
  1: "зтм",
  2: "нет"
}
```

Координаты пересчитываются через:

```text
raw_t10 → T_us = raw_t10 / 10
R_mm    = T_us * speed_m_s / 2000
Y_mm    = R_mm * cos(angle)
X_mm    = R_mm * sin(angle)
```

Для X-позиции графика:

```python
x_px = round(raw * 280 / duration_t10)
```

где `duration_t10` берётся из record/setting.

---

## 7. NASTR2 / настройки

### 7.1 Автовыбор layout

В v34 есть три layout-карты:

| Layout | Назначение |
|---|---|
| `live_prefixed` | основной live RAW с префиксом |
| `live_shifted` | вариант со сдвигом/обрезанным началом на 1 байт |
| `legacy_v14` | fallback для старых сохранённых дампов |

Выбор делается через `select_setting_layout()` и score-функцию. Score учитывает:

```text
- правдоподобную дату;
- скорость УЗК 1000..10000;
- угол 0..90;
- частоту 0.5..10 МГц;
- sweep_type 0..5;
- валидность порогов ВС1/ВС2;
- маркеры shifted-варианта.
```

### 7.2 Основные offsets `live_prefixed`

| Поле | Offset / формула |
|---|---:|
| Частота | `0x04 / 8.0` |
| Дата | `0x06` |
| Время в ПЭП | `LE16(0x10) / 10` |
| № ПЭП | `0x1A`, reverse digit |
| Скорость | `LE16(0x26)` |
| Угол | `LE16(0x28)` |
| Треб. чувств. | `0x43`, отрицательный byte → dB |
| Факт. чувств. | `0x44`, отрицательный byte → dB |
| Усиление | `0x45` |
| Тип развёртки | `0x5C` |
| Длительность | `LE16(0x58)` |
| ВС1 порог/метод/start/end | `0x63 / 0x64 / 0x65 / 0x67` |
| ВС2 порог/метод/start/end | `0x6C / 0x6D / 0x6E / 0x70` |
| ВРЧ type/start/end | `0x7B / 0x7F / 0x81` |
| ВРЧ shape/amp/before/after | `0x87 / 0x88 / 0x89 / 0x8A` |
| Доп. усиление | `0xE7` |

### 7.3 Длительность развёртки type `0x12`

Важная правка:

```text
raw @0x58 = 33
33 * (0xF0 >> 0) / 10 = 792.0 мкс
```

Старое совпадение `270*44/15` отмечено как ложное: `270` — это конец зоны SO, а не длительность.

### 7.4 TYPEVAR в настройках

В коде различаются два класса значений:

```text
1. catalog TYPEVAR:
   3-значные коды вроде 731/834,
   декодируются через оригинальные таблицы zapis2.

2. object-word TYPEVAR:
   Delphi/Pascal words 24667..24672,
   которые обозначают объектные строки.
```

Object-word mapping:

| Код | Текст |
|---:|---|
| `24667` | `ось РУ1` |
| `24668` | `ось РУ1Ш` |
| `24669` | `внут.к-цо подш` |
| `24670` | `нар.к-цо подш` |
| `24671` | `упор.к-цо подш` |
| `24672` | `колесо` |

Отдельно зафиксирован fallback:

```python
SETTING_TYPEVAR_FALLBACK_BY_NO = {26: 731}
```

Смысл:

```text
setting/protocol №26 → TYPEVAR 731
```

---

## 8. SHORTPROT2 / отчёты

### 8.1 Полнота wire-ответа

Отчёт считается структурно полным только если:

```text
1. это не empty marker FD FF / FF FF;
2. len >= 4;
3. LE16(buf+0) == addr;
4. declared = LE16(buf+2) находится в 0x52..0x56;
5. len(buf) >= declared.
```

Если длина `0x55/0x56`, код вычисляет, какой последний checksum byte был бы нужен:

```python
need = (0xFF - (sum(buf) & 0xFF)) & 0xFF
```

Но важно:

```text
байт НЕ синтезируется и НЕ сохраняется как валидный оригинальный record.
Это только диагностическая подсказка.
```

### 8.2 Два layout live-отчётов

`report_body_and_layout()` различает:

| Layout | Признак | Смысл |
|---|---|---|
| `body_only` | обычный короткий body | `record` уже тело отчёта |
| `addr_len_truncated` | `LE16(record+0)==addr` и `LE16(record+2)` около `0x50..0x56` | есть prefix `<addr><len>`, дальше усечённый fragment |

Для `addr_len_truncated` декодер использует более осторожные candidate-offsets.

### 8.3 Поля SHORTPROT2 в v34

Ключевые поправки:

```text
raw[0x06..0x0A] = DD MM YY HH MM
raw[0x05]       = operator code
raw[0x0C]       = К-во дефектов / CODEDEF
```

Очень важная ловушка:

```text
offset 0x07 для даты может давать правдоподобную, но ложную дату.
Пример:
  bytes 01 02 26 09 27
  правильная дата = 01.02.2026 09:27
```

### 8.4 `CODEDEF` в SHORTPROT2

Функция `report_defect_count_643()` фиксирует:

```text
SHORTPROT2.CODEDEF = "К-во деф"
реальный live/raw byte = body[0x0C]
```

Старые варианты `0x2A/0x2E` признаны ошибочными: они часто читали ноль или случайный байт из области TYPEVAR/protocol.

---

## 9. Декод A-протокола / дефекты

### 9.1 Оператор в RESULTS2

В v34:

```text
KODOPERA = record[0x05]
```

Комментарий кода:

```text
raw 0x0C может быть setting/aux byte в 600x
и давал ложные operator codes.
```

### 9.2 Неполные RAW

Если A-scan record короче `0x60`, v34 не пытается насильно добывать поля:

```text
TYPEVAR/NUMOBJ/SMELTING/CODEDEF не сканируются из короткого fragment,
потому что это давало убедительный, но ложный мусор:
  TYPEVAR 512
  NUMOBJ 1111110111
```

В коротком случае сохраняются только безопасные link-поля:

```text
SETTING_NO
SETTING_ADDR
GRAPH_ADDR
SPECIAL
```

### 9.3 Дефект в RESULTS2

Важная поправка:

```text
raw[0x60] НЕ является координатой дефекта и НЕ должен делать DEFEKT='есть'.
```

Текущий код считает дефект подтверждённым только если:

```text
1. цифровое поле CODEDEF около 0x21 выглядит реальным;
2. или оно мапится через оригинальную таблицу defect_text().
```

До завершения точного PelengPC/zapis2 defect-flag offset координаты дефекта обнулены:

```text
defect_y = 0
defect_x = 0
defect_r = 0
defect_t = 0
```

---

## 10. SQLite-модель

Текущие таблицы:

```text
raw_records
raw_events
reports
protocols
settings
protocol_diagnostics
```

### 10.1 `raw_records`

Latest/visible запись по адресу:

```text
address UNIQUE
raw = normalized/latest record
```

### 10.2 `raw_events`

Append-only forensic trace:

```text
каждый 0x42 ответ сохраняется отдельно
raw = wire_raw
```

### 10.3 `reports`

Колонки:

```text
NUMBER, NUMKOD, DATEFORM, TIMEFORM,
KODOPERA, NAMEOPERA, NUMVERS, NUMPRIB,
TYPEVAR, NUMOBJ, SMELTING, CODEDEF, PROTOCOL, NUMZAP
```

`SMELTING` добавляется миграцией, если отсутствует.

### 10.4 `protocols`

Колонки:

```text
NUMBER, NUMKOD, TYPEZAP, DATEFORM, TIMEFORM,
KODOPERA, NAMEOPERA, NUMVERS, NUMPRIB,
TYPEVAR, NUMOBJ, SMELTING, INDMAKER, MAKETIME,
DEFEKT, CODEDEF, SETTING_NO, SETTING_ADDR,
GRAPH_ADDR, SPECIAL, NUMZAP
```

### 10.5 `settings`

Колонки:

```text
NUMBER, NUMKOD, TYPEZAP, DATEFORM, TIMEFORM,
KODOPERA, NAMEOPERA, NUMVERS, NUMPRIB,
SETTING_NO, TYPEVAR, NUMZAP,
params_json
```

`params_json` хранит полный разбор NASTR2.

### 10.6 `protocol_diagnostics`

Диагностическая таблица для связи протокол/график/настройка:

```text
address
linked_graph_addr
setting_addr
fw_code
record_len
graph_found
graph_len
setting_found
setting_no
zones_match_setting
special_geometry
warnings_json
```

Диагностика умеет отмечать:

```text
protocol_short
unexpected_fw_code
bad_setting_no
linked_graph_missing
graph_short
setting_missing
zones_differ_from_current_setting_snapshot
special_geometry_flag_record_0xF0_eq_3
```

---

## 11. Timing profiler

Скрипт содержит `TimingProfiler`, который сохраняет CSV:

```text
cmd
addr
expected_size
started_at
first_at
ended_at
raw_len
declared_len
checksum_ok
status
```

Назначение:

```text
- измерить задержку первого байта после 42;
- измерить gaps/timeout;
- сравнить expected_len с фактической длиной;
- проверить declared len rx[2:4];
- проверить checksum sum == FF.
```

В v34 timing включён по умолчанию:

```python
DEFAULT_TIMING_PROFILE = True
```

---

## 12. Что считать каноном на следующий раунд

### 12.1 Канонический скрипт

```text
peleng_vagon643_full_gui_v34_round46_exact55_clean_logic.py
```

### 12.2 Каноническая live-модель чтения

```text
55:
  один раз → header16 + flat WORD Idx list

42:
  один раз на каждый addr из Idx
  без retry
  без synthetic native slots
  без brute-force settings
  без sort/dedup
  expected_len берётся по диапазону addr
  short/empty/bad-prefix сохраняется как diagnostic raw
```

### 12.3 Канонические live offsets из v34

```python
SETTING_NO_OFF = 0x0D

GRAPH_COPY_LEN  = 0xF4
GRAPH_DRAW_COUNT = 0xF3
GRAPH_BASELINE = 0x8C
GRAPH_WIDTH_ORIG = 0x118
GRAPH_HEIGHT_ORIG = 0x0C8
LINE_FLAG_OFF = 0x128
SPECIAL_GEOMETRY_FLAG_OFF = 0xF0

VS1_THRESHOLD_OFF = 0xB3
VS1_METHOD_OFF = 0xB4
VS1_START_OFF = 0xB5
VS1_END_OFF = 0xB7

VS2_THRESHOLD_OFF = 0xBC
VS2_METHOD_OFF = 0xBD
VS2_START_OFF = 0xBE
VS2_END_OFF = 0xC0

EXTRA_START_OFF = 0xCF
EXTRA_END_OFF = 0xD1
```

### 12.4 Канонические record sizes

```python
LEN_NASTR2     = 0x0176
LEN_ASCAN_4000 = 0x02B6
LEN_BSCAN      = 0x0FD6
LEN_ASCAN_6000 = 0x03A6
LEN_SHORTPROT2 = 0x0056
```

---

## 13. Открытые противоречия / что нужно проверить дизасмом

### 13.1 8N1 vs 8E1

В коде есть два слоя:

```text
комментарии reverse DCB:
  19200 8E1

текущий live clean logic:
  DEFAULT_PARITY = "N"
  GUI label = 19200 8N1
  round43 comment = EVEN parity made 55 Idx unreadable/empty
```

Нужно отдельно вернуться к `PelengPC.exe` в каноническом Ghidra/IDA и проверить:

```text
- где именно задаются ByteSize/Parity/StopBits;
- применим ли этот путь к текущему live обмену;
- нет ли другого профиля порта для ВАГОННАЯ 6.43.
```

Пока для Python-практики фиксируется:

```text
v34 использует 19200 8N1.
```

### 13.2 Round12 offsets vs v34 live offsets

Статическая модель Round12:

```text
setting_no 0x1D
graph 0x1D5
zones 0xC7...
```

v34 live-модель:

```text
setting_no 0x0D с fallback
graph tail/score candidates
zones 0xB3...
```

Это не обязательно взаимоисключение. Вероятнее всего, это разные базы:

```text
zapis2-base / DLL body / clean record / live prefixed record / truncated fragment
```

Нужно формально составить таблицу пересчёта баз для каждой ветки.

### 13.3 График `4000+n` vs `6000+n`

Round12 делал вывод:

```text
4000+n = табличная запись
6000+n = полный график
```

v34 код допускает иное live-наблюдение:

```text
4000+n captured frames can store graph as tail-0xF4;
6000+n extended RESULTS2 also supported, but fixed offset unsafe.
```

Текущий практический подход v34:

```text
строить график из самой считанной A-scan записи,
а offset выбирать heuristically.
```

Нужно проверить на свежих RAW:

```text
- какие адреса реально приходят в 55;
- какой len у 4000+n и 6000+n;
- где score_graph_block выбирает настоящий график.
```

---

## 14. Короткое резюме для будущих запросов

```text
1. Использовать v34 как текущий Python canonical.
2. Не генерировать адреса: читать только exact-55 Idx order.
3. Не сортировать и не дедуплицировать Idx.
4. Не трогать DTR/RTS.
5. Live serial в v34 = 19200 8N1.
6. 42 LL HH: wait(10), без retry.
7. Сохранять wire RAW отдельно от normalized record.
8. Reports 0x52..0x55 при declared 0x56 = incomplete, не валидировать.
9. SHORTPROT2.CODEDEF = body[0x0C] = количество дефектов.
10. A-scan setting_no в live v34 = 0x0D с fallback 0x0C/0x1C/0x1D.
11. Graph в v34 ищется по кандидатам, основной live-кандидат = tail-0xF4.
12. Зоны live graph: ВС1 0xB3..0xB7, ВС2 0xBC..0xC0, ВРЧ 0xCF..0xD1.
13. NASTR2 имеет layouts live_prefixed/live_shifted/legacy_v14.
14. `raw_events` = forensic wire trace; `raw_records` = latest normalized state.
```
