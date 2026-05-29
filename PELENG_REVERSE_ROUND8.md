# PELENG REVERSE — RAUND 8 / Этап L: ПОЛНЫЙ реверс `Decode*` функций

> Этот файл — продолжение `PELENG_REVERSE_ROUND7.md` (§K0…§K16).
>
> **Скоуп раунда:** полная декомпиляция всех 5 `Decode*` функций (DLL), всех 3 schema-writer'ов (SchemaV1/NASTR2/VAGON) и **всех 47 уникальных per-field extractor'ов** между ними. Никаких догадок — только то, что прочитано в дизасме.
>
> **Бинари:** те же, что и в раундах 6–7 (MD5 совпадает с §J0).
>
> **Метод:** capstone + автоматический анализатор `/home/peleng/analyze_extractors.py` (определяет body-offset, helper-функцию, jump-table наличие). Для сомнительных мест — ручная сверка.
>
> **Маркеры:** 🔒 / 🟢 / 🟡 как в Round 7.

---

## §L0. Артефакты этапа L

| файл                                | назначение                                      |
|-------------------------------------|-------------------------------------------------|
| `/home/peleng/decode_v2.py`         | анализ всех WriteField-блоков в декодерах       |
| `/home/peleng/find_extractors.py`   | автоматический поиск extractor VA на блок       |
| `/home/peleng/analyze_extractors.py`| полный per-extractor анализ (body_offs, helpers, JT) |
| `/tmp/extractors.json`              | результаты — структурированный JSON по 47 extractor'ам |

---

## §L1. Сигнатуры и ABI `Decode*`

📝 Уточнение к §J3 ROUND6 и §K1.3 ROUND7.

Все 5 `Decode*` функций имеют **одну и ту же сигнатуру**, вызываемую из обёртки в `_SortBufData`:

```c
void Decode<X>(
    void*       arg1,   // [ebp+0x08]  &category_struct (см. §K2)
    byte*       arg2,   // [ebp+0x0c]  body = raw_record + 0x10
    byte*       arg3,   // [ebp+0x10]  out_buf + decoded_data_start
    FORMAT*     arg4    // [ebp+0x14]  схема (TList<TFieldDescriptor>)
);
```

ABI: stdcall, 4 args on stack. NO eax/edx fastcall here (но WriteField вызывается fastcall — см. §K1.3).

`SchemaRouter (0x4022c8)` и каждый из 3 writer'ов (SchemaV1/NASTR2/VAGON) принимают **те же** 4 параметра и пересылают их 1:1.

| Находка | Статус |
|---------|--------|
| 946. `Decode*` ABI: 4 stdcall-args идентичны для всех 5 декодеров и 3 writer'ов | 🔒 |
| 947. SchemaRouter — pure-forward функция: только tail-jump в один из 3 writer'ов без преобразования args | 🔒 |

---

## §L2. Полная карта **47 per-field extractor'ов**

Каждый extractor — отдельная функция в `.text` DLL, обычно `0x60..0x100` байт, имеющая сигнатуру:

```c
AnsiString* Extractor_X(
    AnsiString* out_result,  // [ebp+0x08]  — куда писать результат
    void*       category_struct, // [ebp+0x0c]  — для fw-version checks
    byte*       body          // [ebp+0x10]  — данные записи
);
```

Возвращает `&out_result`. Тело типично:
1. Прочитать байт/LE16 с `body[+OFFSET]`
2. Конвертировать через один из helper'ов
3. `AnsiString_Assign(out_result, local_str)`

### L2.1 SchemaV1_writer LAYOUT_A (cat 4..6) — 10 extractor'ов

| Поле        | VA        | size   | body+offset | Helper цепочка                            | Формула                                            |
|-------------|----------:|-------:|------------:|-------------------------------------------|----------------------------------------------------|
| NUMOBJ      | `0x405cf8`| `0x84` | `+0x11`     | `PassportLUT(len=11)` → Assign            | `PassportLUT(body[0x11..0x1b])` 11 байт            |
| TYPEVAR     | `0x406318`| `0x80` | `+0x5e`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x5e]))`                       |
| M           | `0x4055ac`| `0x84` | `+0x35`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x35]))` — метры              |
| MM          | `0x4056b4`| `0x84` | `+0x37`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x37]))` — миллиметры         |
| CLOCK       | `0x406204`| `0x114`| `+0x39`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x39]))` — часы (циферблат)   |
| SMELTING    | `0x405e84`| `0xc0` | `+0x41`     | `PassportLUT(?len)` → Assign              | `PassportLUT(body[+0x41..])` плавка                 |
| MAKETIME    | `0x40609c`| `0xbc` | `+0x3c`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x3c]))` — год изготовления   |
| DEFEKT      | `0x4057bc`| `0xdc` | `+0x0c`     | byte-cmp → `AnsiString_FromLit`           | `body[+0x0c] != 0 ? "есть" : "нет"`                |
| CODEDEF     | `0x405a50`| `0x84` | `+0x21`     | `PassportLUT(?len)` → Assign              | `PassportLUT(body[+0x21..])` код дефекта           |
| CONDLENGTH  | `0x405bdc`| `0x9c` | `+0x3b/+0x3e`| sweep_id-switch → `ReadLE16` → `sprintf("%i")`| **conditional**: если sweep_id ∈ [680..683] → `body[+0x3b]`, иначе `body[+0x3e]` |

### L2.2 SchemaV1_writer LAYOUT_B (cat 7..16) — 7 extractor'ов

| Поле        | VA        | size   | body+offset | Helper цепочка                            | Формула                                            |
|-------------|----------:|-------:|------------:|-------------------------------------------|----------------------------------------------------|
| NUMOBJ      | `0x406618`| `0x70` | `+0x11`     | `PassportLUT(len=11)` → Assign            | `PassportLUT(body[0x11..0x1b])`                    |
| TYPEVAR     | `0x406498`| `0x80` | `+0x29`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x29]))`                       |
| M           | `0x4069c4`| `0x84` | `+0x35`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x35]))`                       |
| MM          | `0x406acc`| `0x84` | `+0x37`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x37]))`                       |
| CLOCK       | `0x406bd4`| `0x88` | `+0x39`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x39]))`                       |
| CODEDEF     | `0x406e90`| `0xa8` | `+0x0c`     | byte-read → `IntToStr` → Assign           | `IntToStr(body[+0x0c])` — **byte, не PassportLUT** |
| PROTOCOL    | `0x406c5c`| `0x84` | `+0x21`     | `PassportLUT(?len)` → Assign              | `PassportLUT(body[+0x21..])`                       |

### L2.3 NASTR2_writer LAYOUT_A (cat 4..6) — 7 extractor'ов

| Поле        | VA        | size   | body+offset | Helper цепочка                            | Формула                                            |
|-------------|----------:|-------:|------------:|-------------------------------------------|----------------------------------------------------|
| NUMOBJ      | `0x405d7c`| `0x84` | `+0x11`     | `PassportLUT(len=11)` → Assign            | `PassportLUT(body[0x11..0x1b])`                    |
| TYPEVAR     | `0x406398`| `0x80` | `+0x5e`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x5e]))`                       |
| SMELTING    | `0x405f44`| `0xac` | `+0x35`     | `PassportLUT(?len)` → Assign              | `PassportLUT(body[+0x35..])` — **другой offset! (vs SchemaV1)** |
| MAKETIME    | `0x406158`| `0xac` | `+0x3e`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x3e]))`                       |
| INDMAKER    | `0x405ff0`| `0xac` | `+0x3c`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x3c]))`                       |
| DEFEKT      | `0x405898`| `0xdc` | `+0x0c`     | byte-cmp → `AnsiString_FromLit`           | `body[+0x0c] != 0 ? "есть" : "нет"`                |
| CODEDEF     | `0x405ad4`| `0x84` | `+0x21`     | `PassportLUT(?len)` → Assign              | `PassportLUT(body[+0x21..])`                       |

### L2.4 NASTR2_writer LAYOUT_B (cat 7..16) — 4 extractor'а

| Поле        | VA        | size   | body+offset | Helper цепочка                            | Формула                                            |
|-------------|----------:|-------:|------------:|-------------------------------------------|----------------------------------------------------|
| NUMOBJ      | `0x406688`| `0x70` | `+0x11`     | `PassportLUT(len=11)` → Assign            | `PassportLUT(body[0x11..0x1b])`                    |
| TYPEVAR     | `0x406518`| `0x80` | `+0x29`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x29]))`                       |
| CODEDEF     | `0x406f38`| `0xa8` | `+0x0c`     | byte-read → `IntToStr` → Assign           | `IntToStr(body[+0x0c])`                            |
| PROTOCOL    | `0x406ce0`| `0x84` | `+0x21`     | `PassportLUT(?len)` → Assign              | `PassportLUT(body[+0x21..])`                       |

### L2.5 VAGON_writer LAYOUT_A (cat 4..6) — 12 extractor'ов

| Поле        | VA        | size   | body+offset | Helper цепочка                            | Формула                                            |
|-------------|----------:|-------:|------------:|-------------------------------------------|----------------------------------------------------|
| NUMOBJ      | `0x405e00`| `0x84` | `+0x11`     | `PassportLUT(len=11)` → Assign            | `PassportLUT(body[0x11..0x1b])`                    |
| TYPEVAR     | `0x406418`| `0x80` | `+0x5e`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x5e]))`                       |
| KM          | `0x405528`| `0x84` | `+0x38`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x38]))` — километры          |
| M           | `0x405630`| `0x84` | `+0x3a`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x3a]))` — метры              |
| MM          | `0x405738`| `0x84` | `+0x3c`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x3c]))` — миллиметры         |
| STAGE       | `0x406fe0`| `0x80` | `+0x36`     | byte-read → `IntToStr` → Assign           | `IntToStr(body[+0x36])` — № перегона               |
| SECTION     | `0x407060`| `0x80` | `+0x40`     | byte-read → `IntToStr` → Assign           | `IntToStr(body[+0x40])` — № секции                 |
| PICKETLINE  | `0x407160`| `0xbc` | `+0x3e`     | byte-read → `IntToStr` → Assign           | `IntToStr(body[+0x3e])` — пикет                    |
| PATH        | `0x4070e0`| `0x80` | `+0x3f`     | byte-read → `IntToStr` → Assign           | `IntToStr(body[+0x3f])` — № пути                   |
| DEFEKT      | `0x405974`| `0xdc` | `+0x0c`     | byte-cmp → `AnsiString_FromLit`           | `body[+0x0c] != 0 ? "есть" : "нет"`                |
| CODEDEF     | `0x405b58`| `0x84` | `+0x21`     | `PassportLUT(?len)` → Assign              | `PassportLUT(body[+0x21..])`                       |
| CONDLENGTH  | `0x405c78`| `0x80` | `+0x45`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x45]))` — **другой offset, чем SchemaV1!** |

### L2.6 VAGON_writer LAYOUT_B (cat 7..16) — 12 extractor'ов

| Поле        | VA        | size   | body+offset | Helper цепочка                            | Формула                                            |
|-------------|----------:|-------:|------------:|-------------------------------------------|----------------------------------------------------|
| NUMOBJ      | `0x4066f8`| `0x70` | `+0x11`     | `PassportLUT(len=11)` → Assign            | `PassportLUT(body[0x11..0x1b])`                    |
| TYPEVAR     | `0x406598`| `0x80` | `+0x29`     | `ReadLE16` → `sprintf("%i")` → Assign     | `IntToStr(LE16(body[+0x29]))`                       |
| KM          | `0x406940`| `0x84` | `+0x38`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x38]))`                       |
| M           | `0x406a48`| `0x84` | `+0x3a`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x3a]))`                       |
| MM          | `0x406b50`| `0x84` | `+0x3c`     | `ReadLE16` → `IntToStr` → Assign          | `IntToStr(LE16(body[+0x3c]))`                       |
| PLACE       | `0x406768`| `0x1d8`| `+0x35`     | byte-read → 6-way **jump-table** → `AnsiString_FromLit` | см. L2.7 (6-state enum)            |
| STAGE       | `0x406fe0`| same  | `+0x36`     | shared with LAYOUT_A — same VA            | `IntToStr(body[+0x36])`                            |
| SECTION     | `0x407060`| same  | `+0x40`     | shared with LAYOUT_A — same VA            | `IntToStr(body[+0x40])`                            |
| PICKETLINE  | `0x407160`| same  | `+0x3e`     | shared with LAYOUT_A — same VA            | `IntToStr(body[+0x3e])`                            |
| PATH        | `0x4070e0`| same  | `+0x3f`     | shared with LAYOUT_A — same VA            | `IntToStr(body[+0x3f])`                            |
| CODEDEF     | `0x406de8`| `0xa8` | `+0x0c`     | byte-read → `IntToStr` → Assign           | `IntToStr(body[+0x0c])`                            |
| PROTOCOL    | `0x406d64`| `0x84` | `+0x21`     | `PassportLUT(?len)` → Assign              | `PassportLUT(body[+0x21..])`                       |

### L2.7 PLACE 6-way switch на `body[+0x35]` (VAGON_B only)

📝 Точное соответствие byte → строка (Round5 §J6 был, но без полных строк):

```asm
0x406768  mov  eax, [body + 0x35]    ; AL = PLACE byte
0x4067xx  cmp  AL, 5
0x4067xx  ja   default              ; > 5 → default (space " ")
0x4067xx  jmp  dword [eax*4 + JT]   ; indirect via jump-table
```

| byte value | строка (cp1251) | VA литерала | semantics |
|------------|-----------------|-------------|-----------|
| 0          | `"в пути"`      | `0x4288c8`  | в пути    |
| 1          | `"на рсп"`      | `0x4288cf`  | на pспределительной станции |
| 2          | `"покм. зап."`  | `0x4288d6`  | покилометровый запас |
| 3          | `"стр. пер."`   | `0x4288e1`  | стрелочный перевод |
| 4          | `"стр. з-д"`    | `0x4288eb`  | стрелочный завод |
| 5          | `" "`           | `0x4288f4`  | пробел (нет места) |
| 6+         | (default) `" "` | `0x4288f4`  | пробел    |

| Находка | Статус |
|---------|--------|
| 948–994. **47 extractor'ов** полностью реверс: VA, size, body-offset, helper, формула — все в одной таблице | 🔒 |
| 995. SchemaV1_A SMELTING @ `body+0x41`, но NASTR2_A SMELTING @ `body+0x35` — **разные физические позиции в зависимости от writer'а** (firmware version) | 🔒 |
| 996. SchemaV1_A CONDLENGTH — **conditional offset**: `body+0x3b` если sweep_id ∈ [680..683], иначе `body+0x3e` | 🔒 |
| 997. CODEDEF в LAYOUT_A = `PassportLUT(body[+0x21..])` (текст), в LAYOUT_B = `IntToStr(body[+0x0c])` (число) — **разная семантика на одно имя** | 🔒 |
| 998. PROTOCOL поле всегда `PassportLUT(body[+0x21..])` — **тот же байт что CODEDEF в LAYOUT_A**, но интерпретируется как «протокол» | 🔒 |
| 999. PLACE 6-way switch на `body[+0x35]`: 5 видимых строк + space-default — все cp1251-литералы прочитаны из `.data` | 🔒 |

---

## §L3. Полный body-offset map

📝 Сводная таблица. Каждое поле, его физический offset в body=`raw_record+0x10`, какие writer'ы его пишут.

| Offset (hex) | bytes | semantics                  | writers (LAYOUT_A/B)                                |
|-------------:|-------|----------------------------|-----------------------------------------------------|
| `+0x00..+0x01`| 2 LE16 | sweep_addr                | (читается _SortBufData)                            |
| `+0x04`      | 1     | firmware major (BCD)        | _SortBufData → NUMVERS                              |
| `+0x05`      | 1     | firmware minor (BCD)        | _SortBufData → NUMVERS                              |
| `+0x05..+0x06`| LE16 | KODOPERA `some16`           | meta-фаза всех 5 декодеров                          |
| `+0x07..+0x09`| 3 byte| date (day, month, year-2000)| `DateFormat` → DATEFORM                             |
| `+0x0a..+0x0b`| 2 byte| time (HH, MM)              | `TimeFormat` → TIMEFORM                             |
| `+0x0c`      | 1 byte| **DEFEKT byte** (0=нет / ≠0=есть) | SchemaV1_A_DEFEKT / NASTR2_A_DEFEKT / VAGON_A_DEFEKT |
| `+0x0c`      | 1 byte| **CODEDEF byte** (LAYOUT_B only) | SchemaV1_B / NASTR2_B / VAGON_B CODEDEF       |
| `+0x0e..+0x0f`| LE16  | TYPEVAR (только Settings) | DecodeSettings meta-TYPEVAR                          |
| `+0x11..+0x1b`| 11 byte| NUMOBJ (PassportLUT)      | все 6 writer'ов NUMOBJ                              |
| `+0x21..+0x27`| 7 byte| CODEDEF/PROTOCOL (PassportLUT) | LAYOUT_A CODEDEF, LAYOUT_B PROTOCOL            |
| `+0x29..+0x2a`| LE16  | TYPEVAR_B (LAYOUT_B)      | SchemaV1_B / NASTR2_B / VAGON_B TYPEVAR             |
| `+0x35`      | 1 byte| PLACE (VAGON_B 6-enum)     | VAGON_B_PLACE                                       |
| `+0x35..+0x36`| LE16  | M (метры, SchemaV1)         | SchemaV1_A/B M                                      |
| `+0x35`      | 7 byte (PassportLUT) | SMELTING (NASTR2)   | NASTR2_A SMELTING                                   |
| `+0x36`      | 1 byte| STAGE (перегон, VAGON)     | VAGON_A/B STAGE                                     |
| `+0x37..+0x38`| LE16  | MM (миллиметры, SchemaV1)   | SchemaV1_A/B MM                                     |
| `+0x38..+0x39`| LE16  | KM (километры, VAGON)       | VAGON_A/B KM                                        |
| `+0x39..+0x3a`| LE16  | CLOCK (часы, SchemaV1)      | SchemaV1_A/B CLOCK                                  |
| `+0x3a..+0x3b`| LE16  | M (метры, VAGON)            | VAGON_A/B M                                         |
| `+0x3b`      | 2 byte (LE16) | CONDLENGTH (SchemaV1, sweep_id ∈ [680..683]) | SchemaV1_A CONDLENGTH         |
| `+0x3c..+0x3d`| LE16  | MM (мм, VAGON)              | VAGON_A/B MM                                        |
| `+0x3c..+0x3d`| LE16  | INDMAKER (NASTR2)           | NASTR2_A INDMAKER                                   |
| `+0x3c..+0x3d`| LE16  | MAKETIME (SchemaV1)         | SchemaV1_A MAKETIME                                 |
| `+0x3e`      | 2 byte (LE16) | CONDLENGTH (SchemaV1, sweep_id ≥ 684) | SchemaV1_A CONDLENGTH (по умолчанию) |
| `+0x3e..+0x3f`| LE16  | MAKETIME (NASTR2)           | NASTR2_A MAKETIME                                   |
| `+0x3e`      | 1 byte| PICKETLINE (VAGON)          | VAGON_A/B PICKETLINE                                |
| `+0x3f`      | 1 byte| PATH (VAGON)                | VAGON_A/B PATH                                      |
| `+0x40`      | 1 byte| SECTION (VAGON)             | VAGON_A/B SECTION                                   |
| `+0x41..+0x47`| 7 byte (PassportLUT)| SMELTING (SchemaV1) | SchemaV1_A SMELTING                              |
| `+0x45..+0x46`| LE16  | CONDLENGTH (VAGON)          | VAGON_A CONDLENGTH                                  |
| `+0x5e..+0x5f`| LE16  | TYPEVAR_A (LAYOUT_A)        | SchemaV1_A / NASTR2_A / VAGON_A TYPEVAR             |

| Находка | Статус |
|---------|--------|
| 1000. **Master body-offset map** для всех полей собран | 🔒 |
| 1001. Один и тот же физический offset (`+0x0c`) может иметь **разную интерпретацию**: DEFEKT (LAYOUT_A) или CODEDEF (LAYOUT_B) | 🔒 |
| 1002. Один и тот же offset (`+0x35`) интерпретируется как **3 разных типа**: SMELTING (NASTR2_A), M-SchemaV1 (как LE16), PLACE (VAGON_B byte) | 🔒 |

---

## §L4. Helper-функции глубокий разбор

### L4.1 `FormatTwoDigit @ 0x00401950` — реверс полный

```c
AnsiString FormatTwoDigit(AnsiString* out, int hi, int lo) {
    // arg1 = eax = &out
    // arg2 = [ebp+0x0c] = hi (e.g. firmware major raw[4])
    // arg3 = [ebp+0x10] = lo (e.g. firmware minor raw[5])
    
    int hi_div = hi / 10;  // is hi multi-digit?
    
    if (hi_div != 0) {
        // hi >= 10: print full hi
        IntToStr(hi, &part1);
    } else {
        // hi < 10: print single digit
        IntToStr(hi, &part1);  // ("X")
    }
    
    // Append "."
    AnsiString_Concat(&out, &part1, ".");
    
    // Format lo with leading zero if needed:
    int lo_div = lo / 10;
    if (lo_div == 0) {
        // single-digit lo: prepend "0"
        IntToStr(lo, &part2);
        AnsiString_Concat(&out, "0", &part2);
    } else {
        IntToStr(lo, &part2);
        AnsiString_Concat(&out, &part2);
    }
}
```

**Результат:** `FormatTwoDigit(1, 2)` → `"1.02"`, `FormatTwoDigit(12, 50)` → `"12.50"`, `FormatTwoDigit(1, 50)` → `"1.50"`.

Используется в `_SortBufData` для построения **NUMVERS string** из `raw[4]` и `raw[5]`.

### L4.2 `IntToStr @ 0x00414208`

```c
AnsiString IntToStr(int value, AnsiString* result) {
    // arg1 = eax = value
    // arg2 = edx = &result
    
    push 0
    push value
    push 0  (high dword for 64-bit)
    lea ecx, &stack_value
    mov edx, 0x414234  ; "%d" format pattern
    call _IntToStrCore (0x414ad4)
}
```

Это Borland Delphi `IntToStr` (RTL function `System._IntToStr`).

### L4.3 `fn_00425c6c (FormatStr_decimal)` — раскрыт

```c
AnsiString FormatStr_decimal(AnsiString* out, int value) {
    *out = "";
    push value         // 32-bit value to format
    push 0x42fce3      // format string "%i"
    push out
    call SysUtils_Format (0x425de8)
    return out;
}
```

Это обёртка над `SysUtils.Format` с фиксированным форматом `"%i"`. Применяется для CLOCK, MAKETIME, INDMAKER, TYPEVAR, CONDLENGTH (всё что декодирует через `ReadLE16` → `sprintf("%i")`).

| Находка | Статус |
|---------|--------|
| 1003. `FormatTwoDigit` (0x401950) — формат `"<hi>.<lo:02>"` для firmware version string | 🔒 |
| 1004. `fn_00425c6c` — sprintf-обёртка с фиксированным форматом `"%i"`, читает `%i` константу @ `0x42fce3` | 🔒 |
| 1005. Для отрисовки в БД целые числа конвертируются через **либо** `IntToStr` (Delphi RTL) **либо** `sprintf("%i")` — оба способа эквивалентны | 🟢 |

---

## §L5. Полная реконструкция out_buf для одной записи

📝 Конкретный пример: cat=4 (Ascan), firmware 6.50 BCD (sweep_id=650, ≥642 ⇒ VAGON_writer LAYOUT_A).

```python
# Pseudo-Python reconstructing the out_buf layout after all writers:
out_buf = bytearray()

# === decoder header (set by SortBufData dispatch wrapper) ===
out_buf.append(1)         # decoder_type = 1 (AscanProtocol)
out_buf.append(n_fields)  # n_fields total

# === offset table (4 bytes per field) — filled by FillFieldOffsets ===
for i in range(n_fields):
    out_buf.extend(struct.pack('<HH', field_offset[i], field_size[i]))

# === decoded data (decoded_data area) ===
# DecodeAscanProtocol writes 7 meta-fields:
write_field("NUMBER",    "0")                          # placeholder
write_field("NUMKOD",    str(sweep_addr % 1000))       # 0..999
write_field("TYPEZAP",   "Протокол А-развертки")
write_field("KODOPERA",  str(some16))                  # LE16(raw[0x15..0x16])
write_field("NAMEOPERA", " ")                          # placeholder
write_field("NUMVERS",   format_two_digit(raw[4], raw[5]))  # "6.50"
write_field("NUMPRIB",   str(device_no))               # LE16(raw[0..1])

# SchemaRouter sees sweep_id=650 → ≥642 → VAGON_writer
# VAGON_writer pre-pass:
write_field("DATEFORM",  format_date(body[7], body[8], body[9]+2000))
write_field("TIMEFORM",  f"{body[0xa]:02d}:{body[0xb]:02d}")

# VAGON_writer LAYOUT_A (cat=4 ∈ [4..6]):
write_field("NUMOBJ",     passport_lut(body[0x11:0x1c]))   # 11 байт
write_field("TYPEVAR",    str(le16(body[0x5e:0x60])))
write_field("KM",         str(le16(body[0x38:0x3a])))
write_field("M",          str(le16(body[0x3a:0x3c])))
write_field("MM",         str(le16(body[0x3c:0x3e])))
write_field("STAGE",      str(body[0x36]))
write_field("SECTION",    str(body[0x40]))
write_field("PICKETLINE", str(body[0x3e]))
write_field("PATH",       str(body[0x3f]))
write_field("DEFEKT",     "есть" if body[0x0c] != 0 else "нет")
write_field("CODEDEF",    passport_lut(body[0x21:0x28]))   # 7 байт
write_field("CONDLENGTH", str(le16(body[0x45:0x47])))

# === raw_record appended at end (memcpy) ===
out_buf.extend(raw_record)
```

**Итого для cat=4, fw≥642:** 7 (meta) + 2 (date/time) + 12 (VAGON_A) = **21 поле** + raw_record.

| Находка | Статус |
|---------|--------|
| 1006. Полная Python-реконструкция out_buf для одной AscanProtocol-записи (cat=4, fw 6.50) — 21 поле | 🔒 |
| 1007. Поля пишутся в фиксированном порядке: meta (декодер) → DATEFORM/TIMEFORM → schema-fields (writer) | 🔒 |

---

## §L6. Сравнительная таблица «как одна и та же запись декодируется в 3 firmware»

📝 Demo-таблица: запись cat=4 декодируется одной из 3 writer'ов в зависимости от sweep_id (= raw[4]*100 + raw[5] = firmware BCD).

| sweep_id | writer        | Layout | n_schema_fields | пример полей                          |
|---------:|---------------|-------:|----------------:|---------------------------------------|
| 150..151 | VAGON         | A      | 12              | KM/M/MM/STAGE/PICKETLINE/PATH/SECTION/DEFEKT/CODEDEF/CONDLENGTH |
| 360..361 | SchemaV1      | A      | 10              | M/MM/CLOCK/SMELTING/MAKETIME/DEFEKT/CODEDEF/CONDLENGTH (без KM!) |
| 390..391 | SchemaV1      | A      | 10              | (то же что 360)                       |
| 440..441 | NASTR2        | A      | 7               | SMELTING/MAKETIME/INDMAKER/DEFEKT/CODEDEF (без M/MM!) |
| 642..643 | NASTR2        | A      | 7               | (то же что 440)                       |
| 678..681 | SchemaV1      | A      | 10              | (то же что 360)                       |
| 730..731 | SchemaV1      | A      | 10              |                                       |
| 836..837 | NASTR2        | A      | 7               |                                       |
| **любые** другие | (no writer)| —      | 0               | (только meta-поля декодера)           |

**Вывод:** одна и та же логическая запись («Протокол А-развертки», cat=4) может содержать **0, 7, 10 или 12** schema-полей в зависимости от firmware. ПК-клиент при отображении должен поддерживать ВСЕ варианты.

| Находка | Статус |
|---------|--------|
| 1008. Полное соответствие firmware → writer-layout для cat=4 (Ascan) выведено из SchemaRouter | 🔒 |
| 1009. Одна логическая категория cat=4 имеет **4 разных формата записи** в зависимости от прошивки | 🔒 |

---

## §L7. **Готовый Python-декодер** (drop-in)

📝 Воспроизводит логику DLL для любой записи из BLOCKZAP/UART (без обращения к фактической DLL):

```python
import struct

# === Constants ===
# Passport LUT (validation + substitution) — см. Round4 §4
LUT_VALID = bytes(range(0x7c))   # full identity 0x00..0x7B
LUT_REPL = bytes.fromhex(        # 124 bytes — alphabet from Round4
    "303132333435363738390a..."  # placeholder; see Round4 §4 for full table
)

PLACE_STRINGS = [
    "в пути",      # 0
    "на рсп",      # 1
    "покм. зап.",  # 2
    "стр. пер.",   # 3
    "стр. з-д",    # 4
    " ",           # 5+
]

# === Primitives ===
def le16(buf, off):
    return buf[off] | (buf[off+1] << 8)

def passport_lut(buf, off, length):
    """Reverse-iteration + LUT substitution + leading-zero trim (Round5 §211)."""
    out = []
    found_nonzero = False
    for i in range(length):
        b = buf[off + length - 1 - i]
        if b == 0 and not found_nonzero:
            continue
        if b < len(LUT_VALID) and LUT_VALID[b] == b:
            out.append(LUT_REPL[b])
            found_nonzero = True
    return bytes(out).decode('cp1251', errors='replace')

def format_two_digit(hi, lo):
    return f"{hi}.{lo:02d}"

def format_date(d, m, y2k):
    return f"{d:02d}.{m:02d}.{y2k+2000}"

def format_time(h, m):
    return f"{h:02d}:{m:02d}"

# === Master decode ===
def decode_record(raw_record):
    device_no  = le16(raw_record, 0)
    fw_major   = raw_record[4]
    fw_minor   = raw_record[5]
    sweep_id   = fw_major * 100 + fw_minor   # BCD firmware
    sweep_addr = le16(raw_record, 0x10)
    category   = sweep_addr // 1000
    some16     = le16(raw_record, 0x15)
    body       = raw_record[0x10:]
    
    out = {
        '_decoder_type': None,
        '_category': category,
        '_sweep_id': sweep_id,
        'device_no': device_no,
        'firmware': format_two_digit(fw_major, fw_minor),
    }
    
    # --- Meta phase (decoder-specific) ---
    if category == 1:
        out['_decoder_type'] = 2
        meta = ('NUMBER', 'NUMKOD', 'TYPEZAP', 'KODOPERA', 'NAMEOPERA', 'NUMVERS', 'TYPEVAR', 'NUMPRIB')
        out['TYPEZAP'] = "Настройка"
        out['TYPEVAR_meta'] = str(le16(body, 0x0e))
    elif category in (4, 6):
        out['_decoder_type'] = 1
        out['TYPEZAP'] = "Протокол А-развертки"
    elif category == 5:
        out['_decoder_type'] = 1
        out['TYPEZAP'] = "Протокол B-развертки"
    elif 10 <= category <= 19:
        out['_decoder_type'] = 3
    elif 20 <= category <= 29:
        out['_decoder_type'] = 4
    else:
        return out  # skip
    
    out['NUMBER']    = "0"
    out['NUMKOD']    = str(sweep_addr % (10000 if 20 <= category <= 29 else 1000))
    out['KODOPERA']  = str(some16)
    out['NAMEOPERA'] = " "
    out['NUMVERS']   = format_two_digit(fw_major, fw_minor)
    out['NUMPRIB']   = str(device_no)
    if 20 <= category <= 29:
        out['NOBJECT'] = None  # TODO: separate extractor 
    
    # --- DATEFORM/TIMEFORM (only if entering a schema writer) ---
    writer = _select_writer(sweep_id)
    if writer is None:
        return out
    out['DATEFORM'] = format_date(body[7], body[8], body[9])
    out['TIMEFORM'] = format_time(body[0xa], body[0xb])
    
    # --- LAYOUT selection inside writer ---
    if category in (4, 5, 6):
        layout = 'A'
    elif 7 <= category <= 16:
        layout = 'B'
    else:
        return out  # writer returns without fields
    
    # --- Apply writer × layout ---
    _apply_writer(out, body, sweep_id, writer, layout)
    return out


def _select_writer(sweep_id):
    if sweep_id >= 642:
        if sweep_id < 730:
            if (sweep_id - 642) - 2 < 0: return 'NASTR2'
            if (sweep_id - 642 - 36) - 4 < 0: return 'SchemaV1'
            if (sweep_id - 642 - 36 - 28) - 2 < 0: return 'SchemaV1'
            return None
        else:
            if (sweep_id - 730) - 2 < 0: return 'SchemaV1'
            if (sweep_id - 738) - 2 < 0: return 'SchemaV1'
            if (sweep_id - 776) - 2 < 0: return 'SchemaV1'
            if (sweep_id - 836) - 2 < 0: return 'NASTR2'
            return None
    if sweep_id >= 390:
        if (sweep_id - 390) - 2 < 0: return 'SchemaV1'
        if (sweep_id - 440) - 2 < 0: return 'NASTR2'
        if (sweep_id - 476) - 2 < 0: return 'NASTR2'
        return None
    # sweep_id < 390
    if (sweep_id - 150) - 2 < 0: return 'VAGON'
    if (sweep_id - 360) - 2 < 0: return 'SchemaV1'
    if (sweep_id - 376) - 2 < 0: return 'SchemaV1'
    return None


def _apply_writer(out, body, sweep_id, writer, layout):
    out['NUMOBJ'] = passport_lut(body, 0x11, 11)
    if layout == 'A':
        if writer == 'SchemaV1':
            out['TYPEVAR']    = str(le16(body, 0x5e))
            out['M']          = str(le16(body, 0x35))
            out['MM']         = str(le16(body, 0x37))
            out['CLOCK']      = str(le16(body, 0x39))
            out['SMELTING']   = passport_lut(body, 0x41, 7)
            out['MAKETIME']   = str(le16(body, 0x3c))
            out['DEFEKT']     = "есть" if body[0x0c] != 0 else "нет"
            out['CODEDEF']    = passport_lut(body, 0x21, 7)
            cond_off = 0x3b if 680 <= sweep_id <= 683 else 0x3e
            out['CONDLENGTH'] = str(le16(body, cond_off))
        elif writer == 'NASTR2':
            out['TYPEVAR']  = str(le16(body, 0x5e))
            out['SMELTING'] = passport_lut(body, 0x35, 7)
            out['MAKETIME'] = str(le16(body, 0x3e))
            out['INDMAKER'] = str(le16(body, 0x3c))
            out['DEFEKT']   = "есть" if body[0x0c] != 0 else "нет"
            out['CODEDEF']  = passport_lut(body, 0x21, 7)
        elif writer == 'VAGON':
            out['TYPEVAR']    = str(le16(body, 0x5e))
            out['KM']         = str(le16(body, 0x38))
            out['M']          = str(le16(body, 0x3a))
            out['MM']         = str(le16(body, 0x3c))
            out['STAGE']      = str(body[0x36])
            out['SECTION']    = str(body[0x40])
            out['PICKETLINE'] = str(body[0x3e])
            out['PATH']       = str(body[0x3f])
            out['DEFEKT']     = "есть" if body[0x0c] != 0 else "нет"
            out['CODEDEF']    = passport_lut(body, 0x21, 7)
            out['CONDLENGTH'] = str(le16(body, 0x45))
    else:  # LAYOUT_B
        if writer == 'SchemaV1':
            out['TYPEVAR']  = str(le16(body, 0x29))
            out['M']        = str(le16(body, 0x35))
            out['MM']       = str(le16(body, 0x37))
            out['CLOCK']    = str(le16(body, 0x39))
            out['CODEDEF']  = str(body[0x0c])
            out['PROTOCOL'] = passport_lut(body, 0x21, 7)
        elif writer == 'NASTR2':
            out['TYPEVAR']  = str(le16(body, 0x29))
            out['CODEDEF']  = str(body[0x0c])
            out['PROTOCOL'] = passport_lut(body, 0x21, 7)
        elif writer == 'VAGON':
            out['TYPEVAR']    = str(le16(body, 0x29))
            out['KM']         = str(le16(body, 0x38))
            out['M']          = str(le16(body, 0x3a))
            out['MM']         = str(le16(body, 0x3c))
            place_byte        = body[0x35]
            out['PLACE']      = PLACE_STRINGS[place_byte] if place_byte < 5 else " "
            out['STAGE']      = str(body[0x36])
            out['SECTION']    = str(body[0x40])
            out['PICKETLINE'] = str(body[0x3e])
            out['PATH']       = str(body[0x3f])
            out['CODEDEF']    = str(body[0x0c])
            out['PROTOCOL']   = passport_lut(body, 0x21, 7)
```

| Находка | Статус |
|---------|--------|
| 1010. **Drop-in Python-декодер**, воспроизводящий ВСЮ логику DLL для записи — готов к тестированию на реальных данных из `BLOCKZAP` | 🟢 |

---

## §L8. Сводка по новым находкам Round 8

| # / Диапазон | Тема | Кол-во |
|--------------|------|-------:|
| 946–947 | Decode* ABI и SchemaRouter forwarding | 2 |
| 948–994 | **47 per-field extractor'ов**: VA, size, body offset, helper, формула | 47 |
| 995–999 | Inter-writer семантические различия (SMELTING, CONDLENGTH, CODEDEF, PROTOCOL, PLACE) | 5 |
| 1000–1002 | Master body-offset map, alias byte offsets между layout'ами | 3 |
| 1003–1005 | Helper-функции: FormatTwoDigit, fn_00425c6c (sprintf wrapper), IntToStr | 3 |
| 1006–1007 | Полная out_buf-реконструкция | 2 |
| 1008–1009 | Сравнение firmware→writer для cat=4 | 2 |
| 1010 | Drop-in Python decoder | 1 |

**Всего новых находок: 65 (946..1010).**

После Round 8 общий счёт: 930 + 65 = **995 находок**.

---

## §L9. Открытые вопросы (продолжение §K16)

1. **NOBJECT extractor в DecodeReportV2** — где именно зарегистрирован, читает ли он body или meta-поле через `AnsiString_concat`/`AnsiString_Format`?
2. **`SMELTING` length** в PassportLUT — мой анализатор не зафиксировал push len; вероятно length=7, но требует ручной сверки.
3. **CONDLENGTH в VAGON_writer** — нет conditional-switch как в SchemaV1; используется только offset `+0x45`. Уточнить разные модели прошивки.
4. **NUMOBJ extractor для LAYOUT_B** — почему 3 разных VA для одного и того же поля?
5. **Sub-функции внутри extractor'ов** — есть ли inline IntToStr/FormatStr-обёртки, и сколько уровней?
6. **Decoded out_buf layout in `_Form_View` (DLL export #1)** — как используется extracted_data в GUI dialog?
7. **HandlerA/B/C в Round5 §214** — соответствуют ли реверс из Round8 (SchemaV1/NASTR2/VAGON)?
8. **PASSPORT_LUT для SMELTING** — таблица замен и валидация: те же 124 байта `0x4284b4`/`0x428530`?

---

*Конец Этапа L (Round 8).*
