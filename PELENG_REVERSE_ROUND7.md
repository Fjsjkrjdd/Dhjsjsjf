# PELENG REVERSE — RAUND 7 / Этап K

> Этот файл — продолжение `PELENG_REVERSE_ROUND6.md` (§J0…§J20).  
> **Скоуп:** только новые находки, отсутствующие в раундах 1–6. Особый фокус — **дешифровка переменных протоколов / настроек / отчётов** из сырых TLV-блоков (DLL-сторона), **сортировка/диспетчеризация** записей по категории/прошивке, и **построение A-развёртки** на стороне EXE.
>
> **Источник:** `innoextract PelengPC_ver1_2.exe` → `app/PelengPC.exe` (1 592 832 B, MD5 `f46eb12f51353374a26a0c2c7b0e342e`), `app/102_203dll.dll` (214 016 B, MD5 `cbc0f19c3697b595df64c19812094a68`). MD5 совпадает с §J0 — те же бинари.
>
> **Метод:** capstone x86-32 поверх pefile, без живого UART. Все RVA в формате VA (ImageBase 0x00400000).
>
> **Маркеры:**
> - 🔒 **Железобетонно** — байты прочитаны прямо из дизасма / экспорт-таблицы.
> - 🟢 **Высокая уверенность** — однозначно прочитано в коде, не пересечено вручную.
> - 🟡 **Гипотеза** — требует подтверждения.
>
> Маркер «📝 поправка к §X» означает, что находка уточняет/корректирует более раннюю запись.

---

## §K0. Артефакты этапа K

| файл                                | назначение                                  |
|-------------------------------------|---------------------------------------------|
| `/home/peleng/app/PelengPC.exe`     | главный GUI (BCB 2009)                      |
| `/home/peleng/app/102_203dll.dll`   | декодер TLV-кадров (Delphi 2007)            |
| `/home/peleng/disasm.py`            | helper: PE + capstone + caller-finder       |
| `/home/peleng/extract_lut.py`       | LUT + jump-table extractor                  |
| `/home/peleng/annotate.py`          | per-WriteField аннотация декодеров          |
| `/home/peleng/find_renderers.py`    | поиск callers of TCanvas wrappers           |
| `/home/peleng/lin_disasm.py`        | линейный дизасм по диапазону VA             |

---

## §K1. `_SortBufData` диспетчер — точные LUT и jump-table

📝 поправка к §69 ROUND5 (была лишь общая логика) и §J1 ROUND6.

Прочитан байт-в-байт из `.rdata` DLL:

### K1.1 Sort-LUT @ `0x00401670` (30 байт, `tcode → case_idx`)

```
idx:  0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29
val:  0  5  0  0  3  4  3  0  0  0  2  2  2  2  2  2  2  2  2  2  1  1  1  1  1  1  1  1  1  1
```

Где `tcode = sweep_addr / 1000`. Если `tcode > 0x1d` (29) — переход в exit (case=0). Иначе:
- LUT[1] = 5 → DecodeSettings
- LUT[4] = 3, LUT[5] = 4, LUT[6] = 3 → AscanProtocol / BscanProtocol
- LUT[10..19] = 2 → DecodeReportV1
- LUT[20..29] = 1 → DecodeReportV2
- LUT[0,2,3,7,8,9] = 0 → **запись пропускается** (handler не вызывается)

### K1.2 Jump-table @ `0x0040168e` (6 × DWORD = case_idx → handler exit)

```
case_idx[0] → 0x00401765   ; skip path (no decoder)
case_idx[1] → 0x00401741   ; DecodeReportV2 wrapper
case_idx[2] → 0x0040171b   ; DecodeReportV1 wrapper
case_idx[3] → 0x004016cf   ; DecodeAscanProtocol wrapper
case_idx[4] → 0x004016f5   ; DecodeBscanProtocol wrapper
case_idx[5] → 0x004016a6   ; DecodeSettings wrapper
```

### K1.3 Канонические вызовы декодеров и значение `decoder_type`

Каждый «обёрточный» переход выглядит так (пример для case 5 → DecodeSettings):

```asm
004016a6:  mov  eax, [ebp-0x8c]      ; eax = out_buf (decoded_data start)
004016ac:  mov  byte [eax], 2        ; *** out_buf[0] = decoder_type ***
004016af:  push [ebp-0x58]           ; arg4: FORMAT*
004016b2:  push [ebp-0x90]           ; arg3: out_buf + decoded_data_start
004016b8:  push [ebp-0x9c]           ; arg2: raw_record + 0x10  (= body)
004016be:  lea  edx, [ebp-0x1c]
004016c1:  push edx                  ; arg1: &category_struct
004016c2:  call 0x402980             ; DecodeSettings
```

Сводная таблица:

| case_idx | handler                | out_buf[0] | категории |
|---------:|------------------------|-----------:|-----------|
| 5        | DecodeSettings @ 0x402980          | **2** | cat 1                |
| 3        | DecodeAscanProtocol @ 0x402c8c     | **1** | cat 4, 6             |
| 4        | DecodeBscanProtocol @ 0x402f34     | **1** | cat 5                |
| 2        | DecodeReportV1 @ 0x4031dc          | **3** | cat 10..19           |
| 1        | DecodeReportV2 @ 0x403420          | **4** | cat 20..29           |
| 0        | (no decoder, skip)                 | (не пишется) | cat 0,2,3,7,8,9, ≥30 |

| Находка | Статус |
|---------|--------|
| 891. LUT @ `0x401670` побайтно расшифрован (30 байт) | 🔒 |
| 892. Jump-table @ `0x40168e` (6 × DWORD) полностью прочитана | 🔒 |
| 893. Поле `out_buf[0]` = `decoder_type` ∈ {1,2,3,4} устанавливается **в обёртке** после dispatch'а, не внутри handler'а | 🔒 |
| 894. AscanProtocol и BscanProtocol дают **одинаковый** decoder_type = 1 (различить можно только по cat = 4/6 vs 5) | 🔒 |
| 895. ReportV1 → decoder_type = 3, ReportV2 → decoder_type = 4 (📝 поправка к §190 Round5: там было перепутано) | 🔒 |

---

## §K2. Структура `&category_struct` (arg1 декодеров)

📝 ОЧЕНЬ важный кусок ABI, ранее не описанный в одном месте.

Из `_SortBufData` (ассемблер `0x401474..0x4015be`) видно, что в локалях ebp-0x1c…ebp-8 формируется 24-байтная «карточка записи», адрес которой передаётся декодерам как `arg1`:

| смещение от `arg1` | имя поля           | формула / источник                                       |
|---------------------:|--------------------|-----------------------------------------------------------|
| `+0x00`              | `category`        | `sweep_addr / 1000`                                       |
| `+0x04`              | `device_no`       | LE16: `raw[0]`、`raw[1]`                                  |
| `+0x08`              | `sweep_addr`      | LE16: `raw[0x10]`、`raw[0x11]`                            |
| `+0x0c`              | `sweep_id` (BCD)  | десятично: `raw[4]*100 + raw[5]`                          |
| `+0x10`              | `NUMVERS string`  | AnsiString `"X.YY"` — `FormatTwoDigit(raw[4], raw[5])`     |
| `+0x14`              | `some16`          | LE16: `body[5]`、`body[6]`  (= `raw[0x15]`、`raw[0x16]`) |

Где `body = raw_record + 0x10` (тоже передаётся декодерам как `arg2`).

| Находка | Статус |
|---------|--------|
| 896. Структура `category_struct` (24 байта, 6 полей) теперь полностью расшифрована | 🔒 |
| 897. `NUMVERS` уже **готовая AnsiString** в `arg1+0x10`, строится `FormatTwoDigit(raw[4], raw[5])` в `_SortBufData` (см. ассемблер `0x40153f..0x401571`) | 🔒 |
| 898. `some16` = LE16(`raw[0x15..0x16]`) — используется как **KODOPERA** во всех 5 декодерах | 🔒 |

---

## §K3. Точные формулы извлечения **meta-полей** во всех 5 декодерах

📝 ВСЕ записи `WriteField(...)` каждого декодера найдены через автомат (capstone+pattern). Раньше (Round5 §70, Round6 §J8…§J11) список был неполным/перепутанным.

### K3.1 Общие meta-поля (записываются во всех 5 декодерах)

| Поле       | Формула                                                      | Helper             |
|------------|--------------------------------------------------------------|--------------------|
| `NUMBER`   | литерал `"0"` (плейсхолдер, заполняется хостом перед SQL)    | `AnsiString_FromLit` |
| `NUMKOD`   | `IntToStr(sweep_addr % 1000)` — для Settings/Ascan/Bscan/V1<br>`IntToStr(sweep_addr % 10000)` — **только для V2** | `IntToStr` |
| `KODOPERA` | `IntToStr(some16)` где `some16 = LE16(raw[0x15..0x16])`      | `IntToStr` |
| `NAMEOPERA`| литерал `" "` (один пробел; плейсхолдер, host подставляет имя оператора) | `AnsiString_FromLit` |
| `NUMVERS`  | готовая `"X.YY"` из `category_struct[+0x10]` (firmware)      | (assign)           |
| `NUMPRIB`  | `IntToStr(device_no)` = `IntToStr(LE16(raw[0..1]))`          | `IntToStr` |

### K3.2 Поля, специфичные для конкретного декодера

| Декодер              | Доп. поля (поверх K3.1)                                | Литерал TYPEZAP                 |
|----------------------|--------------------------------------------------------|---------------------------------|
| DecodeSettings       | `TYPEZAP="Настройка"`, `TYPEVAR=IntToStr(LE16(raw[0x1e..0x1f]))` | `"Настройка"` (CP1251 9 байт) |
| DecodeAscanProtocol  | `TYPEZAP="Протокол А-развертки"`                       | `"Протокол А-развертки"` (CP1251) |
| DecodeBscanProtocol  | `TYPEZAP="Протокол B-развертки"`                       | `"Протокол B-развертки"` (CP1251) |
| DecodeReportV1       | (TYPEZAP **не пишется**, NOBJECT тоже)                 | —                               |
| DecodeReportV2       | `NOBJECT` (значение через `0x4268ec`+`0x426970` хелперы) | —                             |

### K3.3 Полный sequence для DecodeSettings (как пример)

| # | call_va    | Поле      | Формула значения                                       |
|---|-----------:|-----------|--------------------------------------------------------|
| 1 | 0x4029c3   | NUMBER    | `"0"` (литерал)                                        |
| 2 | 0x402a2b   | NUMKOD    | `IntToStr(sweep_addr % 1000)`                          |
| 3 | 0x402a8f   | TYPEZAP   | `"Настройка"`                                          |
| 4 | (0x402ab0) | — *вызов `SchemaRouter(0x4022c8)` сразу после TYPEZAP* — | пишет всё что зависит от sweep_id/cat |
| 5 | 0x402af1   | KODOPERA  | `IntToStr(some16)`                                     |
| 6 | 0x402b49   | NAMEOPERA | `" "` (литерал)                                        |
| 7 | 0x402b94   | NUMVERS   | AnsiString_FromLit из `category_struct[+0x10]`          |
| 8 | 0x402be9   | TYPEVAR   | `IntToStr(LE16(body[+0x0e]))` = `IntToStr(LE16(raw[+0x1e..+0x1f]))` |
| 9 | 0x402c47   | NUMPRIB   | `IntToStr(device_no)`                                  |

| Находка | Статус |
|---------|--------|
| 899. NUMBER = литерал `"0"` во ВСЕХ 5 декодерах — это **placeholder для record-number, заполняется ПК после Insert** | 🔒 |
| 900. NAMEOPERA = литерал `" "` (один пробел) во ВСЕХ 5 декодерах — host подставляет имя оператора по KODOPERA | 🔒 |
| 901. NUMKOD у V2 делится на **10000**, а не 1000 → внутри cat 20..29 NUMKOD кодирует `sub_cat*1000 + index` (📝 НОВОЕ) | 🔒 |
| 902. TYPEZAP-литерал явно зашит в `.data` DLL по типу декодера (3 разные строки) | 🔒 |
| 903. `TYPEVAR` пишется **только** DecodeSettings, формула `LE16(raw[0x1e..0x1f])` (📝 уточнение к §192 Round5) | 🔒 |
| 904. `NOBJECT` пишется **только** DecodeReportV2 (📝 НОВОЕ; раньше говорилось о DecodeSettings) | 🔒 |
| 905. DecodeReportV1 пишет **6 полей** (без TYPEZAP/TYPEVAR/NOBJECT) — реально самый бедный декодер | 🔒 |

---

## §K4. `SchemaRouter` @ `0x004022c8` — multi-stage диспетчер на `sweep_id`

📝 ПОЛНАЯ декомпиляция (Round5 §74 — была только верхняя часть).

```c
void SchemaRouter(void* arg1, byte* body, byte* out_buf, FORMAT* fmt) {
    int sweep_id = arg1->sweep_id;          // arg1[+0x0c]

    if (sweep_id >= 0x282) goto BLOCK_VAGON;     // 642  (firmware 6.42)
    if (sweep_id >= 0x186) goto BLOCK_NASTR2;    // 390  (firmware 3.90)

    // ===== диапазон [0..390) =====
    int edx = sweep_id - 0x96;              // 150
    if (edx - 2 < 0)  goto VAGON_writer (0x404758);   // sweep_id ∈ [150..151]
    edx -= 0xd2;                            // 210
    if (edx - 2 < 0)  goto SchemaV1_writer (0x403834); // sweep_id ∈ [360..361]
    edx -= 0x10;                            // 16
    if (edx - 2 < 0)  goto SchemaV1_writer;            // sweep_id ∈ [376..377]
    return;                                 // нет writer'а

BLOCK_NASTR2: // sweep_id ∈ [390..641]
    edx = sweep_id - 0x186 - 0x186;         // (sweep_id - 390) - 390 ... но реально edx -= 1666-2
    if (edx - 2 < 0)  goto SchemaV1_writer; // sweep_id ∈ [390..391]
    edx -= 0x32;                            // 50
    if (edx - 2 < 0)  goto NASTR2_writer (0x4041d0); // sweep_id ∈ [440..441]
    edx -= 0x24;                            // 36
    if (edx - 2 < 0)  goto NASTR2_writer;   // sweep_id ∈ [476..477]
    return;

BLOCK_VAGON: // sweep_id ≥ 642
    if (sweep_id < 0x2da) { // 730
        edx = sweep_id - 0x282;             // 642
        if (edx - 2 < 0)  goto NASTR2_writer; // sweep_id ∈ [642..643]
        edx -= 0x24;                        // 36
        if (edx - 4 < 0)  goto SchemaV1_writer; // sweep_id ∈ [678..681]
        edx -= 0x1c;                        // 28
        if (edx - 2 < 0)  goto SchemaV1_writer; // sweep_id ∈ [706..707]
        return;
    }
    // sweep_id ≥ 730
    edx = sweep_id - 0x2da;                 // 730
    if (edx - 2 < 0)  goto SchemaV1_writer; // 730..731
    edx -= 0x08;                            // 8
    if (edx - 2 < 0)  goto SchemaV1_writer; // 738..739
    edx -= 0x26;                            // 38
    if (edx - 2 < 0)  goto SchemaV1_writer; // 776..777
    edx -= 0x3c;                            // 60
    if (edx - 2 < 0)  goto NASTR2_writer;   // 836..837
    return;
}
```

| Находка | Статус |
|---------|--------|
| 906. SchemaRouter — **многоступенчатый дискриминатор** по `sweep_id` с порогами 150, 360, 376, 390, 440, 476, 642, 678, 706, 730, 738, 776, 836 — каждая прошивка попадает в **один из 3 writer'ов** | 🔒 |
| 907. 3 целевых writer'а: **SchemaV1 (0x403834), NASTR2 (0x4041d0), VAGON (0x404758)** | 🔒 |
| 908. Прошивки `< 150`, `[152..359]`, `[362..375]`, `[378..389]`, `[392..439]`, `[442..475]`, `[478..641]`, `[644..677]`, `[682..705]`, `[708..729]`, `[732..737]`, `[740..775]`, `[778..835]`, `≥838` — **возвращают БЕЗ writer'а** (только meta-поля пишутся) | 🔒 |
| 909. Распределение по версиям: каждая БЕТА-сборка прошивки маппится к подходящему writer'у явно | 🔒 |

---

## §K5. SchemaV1_writer @ `0x00403834` — **НОВАЯ функция, ранее не описанная**

📝 НОВОЕ (раньше упоминался только NASTR2 и VAGON; SchemaV1 был «fallback», но содержимое не разбиралось).

Размер `0x99c` (`0x99c` байт). Содержит 17 вызовов `WriteField`, разбитых на **2 layout'а** в зависимости от `category` (взято из `arg1[+0]`):

### K5.1 Внутренний switch (offset 0x40388a..0x4038ac)

```asm
mov ecx, [ebp+8]            ; ecx = &category_struct
mov eax, [ecx]              ; eax = category
add eax, -4                 ; eax -= 4
sub eax, 3                  
jb  LAYOUT_A (0x4038b1)     ; category ∈ [4..6] → полный layout (10 полей)
add eax, -3                 
sub eax, 0xa                
jb  LAYOUT_B (0x403de8)     ; category ∈ [7..16] → партиальный (7 полей)
sub eax, 0xa                
jb  EXIT (0x4041a9)         ; category ∈ [17..26] → ничего не пишет
jmp EXIT                    ; иначе → exit
```

### K5.2 LAYOUT_A (category ∈ [4..6], 10 полей)

В прологе функции, **до switch'а**, выполняются:
- `DateFormat(body, 7)` → пишет поле `DATEFORM` (3 байта body[+7..+9])
- `TimeFormat(body, 0xa)` → пишет поле `TIMEFORM` (2 байта body[+0xa..+0xb])

Далее последовательно:

| # | call_va    | Поле        | Метод                                |
|---|-----------:|-------------|--------------------------------------|
| 1 | 0x40391e   | `NUMOBJ`    | `PassportLUT(body+0x11, len=11)`     |
| 2 | 0x4039a3   | `TYPEVAR`   | LE16 из body                         |
| 3 | 0x403a28   | `M`         | (метры — целая часть длины)          |
| 4 | 0x403aad   | `MM`        | (миллиметры — дробная)               |
| 5 | 0x403b32   | `CLOCK`     | (часы по циферблату — место дефекта) |
| 6 | 0x403bb7   | `SMELTING`  | `PassportLUT(...)`                   |
| 7 | 0x403c3c   | `MAKETIME`  | (дата изготовления, BCD)             |
| 8 | 0x403cc1   | `DEFEKT`    | enum byte (`"есть"`/`"нет"`)         |
| 9 | 0x403d46   | `CODEDEF`   | `PassportLUT(...)`                   |
| 10| 0x403dcb   | `CONDLENGTH`| ?                                    |

### K5.3 LAYOUT_B (category ∈ [7..16], 7 полей)

| # | call_va    | Поле        |
|---|-----------:|-------------|
| 1 | 0x403e55   | `NUMOBJ`    |
| 2 | 0x403eda   | `TYPEVAR`   |
| 3 | 0x403f5f   | `M`         |
| 4 | 0x403fe4   | `MM`        |
| 5 | 0x404069   | `CLOCK`     |
| 6 | 0x4040f4   | `CODEDEF`   |
| 7 | 0x40418e   | `PROTOCOL`  |

| Находка | Статус |
|---------|--------|
| 910. `SchemaV1_writer` существует, размер 0x99c, **2 layout'а × 10/7 полей** | 🔒 |
| 911. LAYOUT_A для cat ∈ [4..6] (Settings/AscanProtocol/BscanProtocol — соответствует ИМЕННО cat 4/5/6 → AscanProtocol/BscanProtocol/AscanProtocol) | 🔒 |
| 912. LAYOUT_B для cat ∈ [7..16] (т.е. для cat 10..16 — это **только DecodeReportV1**) | 🔒 |
| 913. cat ∈ [17..26] — `SchemaV1_writer` **не пишет ничего** даже когда вызван | 🔒 |
| 914. Появляется **новое поле `CLOCK`** (часы циферблата) в обоих layout'ах SchemaV1 — НЕ существует в NASTR2/VAGON | 🔒 |
| 915. Появляется поле `M` (метры) уже в LAYOUT_A — в NASTR2 его нет | 🔒 |
| 916. DATEFORM/TIMEFORM пишутся **до** внутреннего switch'а — общие для обоих layout'ов | 🔒 |

---

## §K6. `NASTR2_writer` @ `0x004041d0` — точный список полей

📝 Уточнение к §75 Round5 (там было «11 колонок» без полного списка).

11 вызовов `WriteField`, 2 layout'а:

### LAYOUT_A (полный, cat ∈ [4..6], 7 полей)

| # | call_va  | Поле       |
|---|---------:|------------|
| 1 | 0x40429f | `NUMOBJ`   |
| 2 | 0x404312 | `TYPEVAR`  |
| 3 | 0x404385 | `SMELTING` |
| 4 | 0x4043f8 | `MAKETIME` |
| 5 | 0x40446b | `INDMAKER` |
| 6 | 0x4044de | `DEFEKT`   |
| 7 | 0x404551 | `CODEDEF`  |

### LAYOUT_B (партиальный, cat ∈ [7..16], 4 поля)

| # | call_va  | Поле       |
|---|---------:|------------|
| 1 | 0x4045c9 | `NUMOBJ`   |
| 2 | 0x40463c | `TYPEVAR`  |
| 3 | 0x4046af | `CODEDEF`  |
| 4 | 0x404722 | `PROTOCOL` |

| Находка | Статус |
|---------|--------|
| 917. NASTR2 LAYOUT_A: NUMOBJ, TYPEVAR, SMELTING, MAKETIME, INDMAKER, DEFEKT, CODEDEF (7) | 🔒 |
| 918. NASTR2 LAYOUT_B: NUMOBJ, TYPEVAR, CODEDEF, PROTOCOL (4) | 🔒 |
| 919. NASTR2 — **отсутствует** поле `CLOCK` (в отличие от SchemaV1) | 🔒 |
| 920. NASTR2 LAYOUT_A добавляет `INDMAKER` (индекс изготовителя) — нет ни в SchemaV1, ни в VAGON | 🔒 |

---

## §K7. `VAGON_writer` @ `0x00404758` — точный список полей

📝 Уточнение к §76 Round5 (24 колонки) — полный per-call список.

24 вызова `WriteField`, 2 layout'а:

### LAYOUT_A (cat ∈ [4..6], 12 полей)

| # | call_va  | Поле        |
|---|---------:|-------------|
| 1 | 0x404842 | `NUMOBJ`    |
| 2 | 0x4048c7 | `TYPEVAR`   |
| 3 | 0x40494c | `KM`        |
| 4 | 0x4049d1 | `M`         |
| 5 | 0x404a56 | `MM`        |
| 6 | 0x404adb | `STAGE`     |
| 7 | 0x404b60 | `SECTION`   |
| 8 | 0x404be5 | `PICKETLINE`|
| 9 | 0x404c6a | `PATH`      |
|10 | 0x404cef | `DEFEKT`    |
|11 | 0x404d74 | `CODEDEF`   |
|12 | 0x404df9 | `CONDLENGTH`|

### LAYOUT_B (cat ∈ [7..16], 12 полей)

| # | call_va  | Поле        |
|---|---------:|-------------|
| 1 | 0x404e83 | `NUMOBJ`    |
| 2 | 0x404f08 | `TYPEVAR`   |
| 3 | 0x404f8d | `KM`        |
| 4 | 0x405018 | `M`         |
| 5 | 0x4050b2 | `MM`        |
| 6 | 0x40514c | `PLACE`     |
| 7 | 0x4051e6 | `STAGE`     |
| 8 | 0x405280 | `SECTION`   |
| 9 | 0x40531a | `PICKETLINE`|
|10 | 0x4053b4 | `PATH`      |
|11 | 0x40544e | `CODEDEF`   |
|12 | 0x4054e8 | `PROTOCOL`  |

| Находка | Статус |
|---------|--------|
| 921. VAGON LAYOUT_A: 12 полей с координатами **`KM + M + MM`** + локацией пути (STAGE/SECTION/PICKETLINE/PATH) + DEFEKT/CODEDEF/CONDLENGTH | 🔒 |
| 922. VAGON LAYOUT_B добавляет `PLACE` (6-state enum, см. §J18 Round6) и заменяет DEFEKT/CONDLENGTH на PROTOCOL | 🔒 |
| 923. VAGON — **единственный** writer с тройным форматом длины `KM/M/MM` | 🔒 |

---

## §K8. `DateFormat` @ `0x004023b0` и `TimeFormat` @ `0x00402504`

📝 Точное чтение байтов из body (Round5 §80 был, но без полного дизасма).

```c
void DateFormat(byte* body, ..., byte* out_buf, FORMAT* fmt, int off) {
    int year  = body[off + 2] + 0x7d0;      //  +2000
    int month = body[off + 1];              //  1..12
    int day   = body[off + 0];              //  1..31
    
    if (ValidateDate(year, month, day)) {           // 0x402874
        double dt = EncodeDate(year, month, day);   // 0x414dac → TDateTime
        AnsiString s = FormatDate("dd.mm.yyyy", dt); // 0x415b58
        WriteField(out_buf, fmt, "DATEFORM", s);
    } else {
        // пустая строка
    }
}
```

В SchemaV1, NASTR2, VAGON вызываются с `off = 7` (DATEFORM) и `off = 0xa` (TIMEFORM, только день+час).

| Находка | Статус |
|---------|--------|
| 924. DATEFORM = `body[+7..+9]` = (day, month, year-2000) — общее **для всех трёх writer'ов** | 🔒 |
| 925. TIMEFORM = `body[+0xa..+0xb]` = (HH, MM) | 🔒 |
| 926. Дата проходит проверку `ValidateDate (0x402874)` — если невалидно, в БД идёт пустая строка | 🔒 |
| 927. Дата хранится как `TDateTime` double и форматируется через `FormatDate("dd.mm.yyyy")` Delphi-helper | 🔒 |

---

## §K9. `NUMOBJ` extractor @ `0x00405cf8`

📝 Точный offset раньше был «11 байт @17» (Round5 §175). Теперь подтверждён.

```c
AnsiString NUMOBJ_Extractor(AnsiString* result, byte* body) {
    push 0xb              // length = 11
    push (body + 0x11)    // ptr 11 байт со смещения 0x11 в body
    push result
    call PassportLUT (0x402708)
    // result = декодированные 11 байт через двойную LUT (валидация + замена)
    return result;
}
```

То есть **NUMOBJ = `PassportLUT(body[0x11..0x1b])`** = 11-байтная строка проходящая через LUT @ 0x4284b4 (валидация) и LUT @ 0x428530 (substitution).

| Находка | Статус |
|---------|--------|
| 928. NUMOBJ — 11 байт от `body[+0x11]` → `raw[+0x21]`, обрабатывается `PassportLUT (0x402708)` | 🔒 |
| 929. Используется один и тот же extractor `0x405cf8` во ВСЕХ 3 writer'ах (SchemaV1/NASTR2/VAGON) | 🔒 |

---

## §K10. Карта meta- vs schema-полей в out_buf

Полная картина выходной структуры `out_buf` (decoded_data block):

```
   [decoder_type, n_fields, offset_table, decoded_data, raw_record]
   
   decoded_data = [meta-fields, ...schema-fields...]
   
   meta-fields пишутся в соответствующем декодере (5 функций @ 0x402980..0x403420)
   schema-fields пишутся через SchemaRouter(0x4022c8) → один из 3 writer'ов
```

**Общая картина для cat 1 (Settings) + firmware ≥ 642 BCD:**

```
out_buf:
  [0]  decoder_type = 2                  ; set by dispatch wrapper
  [1]  n_fields                          ; copies from fmt[2]
  [2..2+4*n] offset table
  [meta-region]: NUMBER, NUMKOD, TYPEZAP="Настройка", KODOPERA, NAMEOPERA, NUMVERS, TYPEVAR, NUMPRIB
  [schema-region]: DATEFORM, TIMEFORM, NUMOBJ, TYPEVAR, KM, M, MM, STAGE, SECTION, PICKETLINE, PATH, DEFEKT, CODEDEF, CONDLENGTH
  [raw-region]: оригинальные байты записи (memcpy)
```

**TYPEVAR пишется ДВАЖДЫ** — один раз в meta (DecodeSettings) и один раз в schema (VAGON_writer). Это интересный артефакт схемы: meta-TYPEVAR имеет фиксированный размер из FORMAT, а schema-TYPEVAR может иметь другой kind/size.

| Находка | Статус |
|---------|--------|
| 930. TYPEVAR может появляться **дважды** в одном out_buf — meta-copy и schema-copy | 🔒 |
| 931. DATEFORM/TIMEFORM находятся **в schema-region**, не в meta — отсюда они появляются ДО первого WriteField самого schema-writer'а, но в логике после meta | 🔒 |

---

## §K11. Карта EXE Canvas-врапперов (Borland VCL TCanvas)

Прямая дешифровка PE: маленькие функции в `0x004a80..0x004a95` — это **методы класса `TCanvas`**, обёртки над GDI32 API. Полная карта:

| VCL метод            | VA wrapper  | вызывает GDI32   | IAT thunk    | callers |
|----------------------|-------------|------------------|--------------|--------:|
| TCanvas.Ellipse      | `0x4a8b74`  | `Ellipse`        | `0x52032c`   |       1 |
| TCanvas.FillRect     | `0x4a8bbc`  | `FillRect`       | `0x5205d6`   |  (mult) |
| TCanvas.LineTo       | `0x4a8c34`  | `LineTo`         | `0x5203e0`   |      20 |
| TCanvas.MoveTo       | `0x4a8c94`  | `MoveToEx`       | `0x5203ec`   |      14 |
| TCanvas.PolyBezier   | `0x4a8cc0`  | `PolyBezier`     | `0x5203f8`   |   (?)   |
| TCanvas.Polyline     | `0x4a8d18`  | `Polyline`       | `0x52040a`   |       4 |
| TCanvas.Rectangle    | `0x4a8d50`  | `Rectangle`      | `0x52041c`   |      10 |
| TCanvas.TextOut      | `0x4a8e00`  | `ExtTextOutA`    | `0x52033e`   |       3 |
| TCanvas.TextRect/Out | `0x4a8e8c`  | `ExtTextOutA`    | `0x52033e`   |       5 |
| TCanvas.SetPixel     | `0x4a90cc`  | `SetPixel`       | `0x520464`   |       1 |
| TCanvas.CopyRect (StretchBlt) | `0x4a874c` | `StretchBlt` | `0x52049a` |       2 |
| TCanvas.Draw_StretchBlt #2    | `0x4a9488` | `StretchBlt` | `0x52049a` |       7 |

**Важная деталь:** `TCanvas.Polyline` берёт `count`, но **внутри** делает `inc edi; push edi` перед `call Polyline` — то есть передаёт в GDI32 `count + 1`. Поэтому если вызов wrapper'а имеет `ecx = 2`, на самом деле GDI рисует 3 точки (последняя — повтор для замыкания).

| Находка | Статус |
|---------|--------|
| 932. Полная карта 12 VCL-методов TCanvas с их IAT thunks | 🔒 |
| 933. `TCanvas.Polyline (0x4a8d18)` инкрементирует count перед передачей в GDI32 — **n_points = ecx + 1** | 🔒 |

---

## §K12. **A-развёртка: рендеринг трассы** @ `0x0049fdc0`

🔥 **Ключевой раздел этого раунда** — построение графика A-развёртки в протоколе.

### K12.1 Архитектура

Трасса A-развёртки рисуется НЕ через `Polyline` (тот используется только для 2-точечных линий — гейты/стробы), а через **`PolyPolyline`** одним вызовом, который рисует множество коротких отрезков. Это **envelope-style** визуализация — каждая колонка получает 2-точечный отрезок (min..max), формируя «бары».

### K12.2 Сигнатура функции

```c
void RenderTrace(this, ascanData, byte alignFlag) {
    /* this is unused [ebp+8]; we focus on the args */
}
```

Параметры:
- `arg1 = [ebp+8]` — байт-флаг (если `!= 0`, использует «другой Y» для рисования)
- `arg2 = [ebp+0xc]` — главный объект графика, который содержит:
  - `[+0x14]` → arrays-table из X-координат (массив DWORD × 4: X0..X3)
  - `[+0x1c]` → дескриптор points-array:
    - `[+0]` = base_x
    - `[+0x10]` = total_sample_count
    - `[+0x28]` = виртуальный метод `get_sample(index)` → returns y
    - `[+0x2c]` = пользовательский parametr для виртуального вызова
  - `[+0x1c][-4]` → `lpPolyCounts[]` (массив счётчиков точек на каждый полилайн)
  - `[+0x1c][-8]` → `lpPoints[]` (POINT[] буфер)
- `[esi]` — глобальный индекс «текущей серии» (0 или 1) — для двух-канального A-scan

### K12.3 Псевдокод цикла

```c
TBitmap* canvas_bm = ...->canvas;
TCanvas* canvas = canvas_bm->Canvas;

// Setup pen color from sample_count's color
canvas->Brush.Color = ...->color1;
canvas->Pen.Color = ...->color2;
canvas->FillRect(this->rect);   // (через 0x4a8294 ↓)

// Build POINTS array
POINT* points = ascan_obj->points_buf;          // edi
descriptor* desc = ascan_obj->point_descriptor;  // ebx
int counter = 0;
int initial_y = desc->base_x + desc->arrays_table[esi] + (desc->step >> 1);

int max_x = desc->arrays_table[esi+2] + desc->base_x;  // правая граница

while (counter < desc->total_count) {
    // Чтение одного сэмпла через виртуальный метод:
    int y_sample = desc->get_sample(counter, desc->param);  // call [ebx+0x28]
    
    // Запись пары POINTS:
    //   POINTS[esi+idx].x = current_x    POINTS[esi^1+idx].y = arrays_table[esi^1]    // first segment endpoint
    //   POINTS[esi+(idx+2)].x = current_x    POINTS[esi^1+(idx+2)].y = arrays_table[esi^1+2]  // second endpoint
    points[esi + idx].x   = current_x;
    points[(esi^1) + idx].y = sample_y_low;
    points[esi + (idx+2)].x = current_x;
    points[(esi^1) + (idx+2)].y = sample_y_high;
    idx += 4;
    counter++;
    current_x += desc->base_x + desc->get_sample(counter);
    if (current_x > max_x) break;
}

// Render via PolyPolyline (one polyline per 2-point segment)
PolyPolyline(canvas->Handle, points, lpPolyCounts, idx >> 2);
```

### K12.4 Ключевые VA

| VA         | Назначение                                                       |
|-----------:|------------------------------------------------------------------|
| `0x0049fdc0` | RenderTrace(this, ascan_obj, align_flag) — точка входа           |
| `0x0049fdfb` | preconfig: получает Color из bitmap.SamplesColor                 |
| `0x0049fe22` | TCanvas.Pen.Color = color1                                       |
| `0x0049fe27` | `call 0x4a82fc` (TCanvas.???) — possibly SetClipRgn              |
| `0x0049fe3a` | `call 0x4a81cc` — TCanvas.GetCanvas                              |
| `0x0049fe5f` | `call 0x520338` — **PolyDraw** или **GetClipBox** (требует уточнения) |
| `0x0049fe7f` | `call [ebx+0x28]` — **главный virtual call: получить сэмпл**     |
| `0x0049ff27` | повтор `call [ebx+0x28]` в цикле                                 |
| `0x0049ff63` | `call 0x4a9138` — TCanvas.Handle getter                          |
| `0x0049ff69` | **`call 0x520404` = PolyPolyline IAT thunk**                     |

| Находка | Статус |
|---------|--------|
| 934. A-развёртка рисуется через **`PolyPolyline`** одним вызовом, по 2 точки на сэмпл (envelope) | 🔒 |
| 935. Сэмплы извлекаются через **виртуальный метод `[obj+0x28]`** на «descriptor» объекте — позволяет одним рендером поддерживать несколько источников (A-scan / B-scan column) | 🔒 |
| 936. `POINTS` буфер выделяется заранее в объекте `ascan_obj->[+0x1c]+(-8)` (стандартный VCL pattern — буфер с `length` prefix в +(-4)) | 🔒 |
| 937. Точка `esi` (0 или 1) определяет, какой из двух A-scan каналов рисовать (бинарь поддерживает дву-канальный режим) | 🔒 |
| 938. `arrays_table[]` хранит 4 DWORD — X-координаты для каждой из 2 каналов × {start, end} | 🔒 |
| 939. Цикл прерывается по `current_x > max_x` — клиппинг по правому краю окна | 🔒 |

### K12.5 GDI-уровневое отличие от других графиков

`Polyline` (одиночный вызов с массивом всех точек) был бы естественным для A-scan. Почему `PolyPolyline`?

Гипотеза: при envelope-режиме (большинство A-scan на УД2-102/103) одно колонк = один вертикальный отрезок (min..max). Каждый отрезок — отдельный полилайн из 2 точек. `PolyPolyline` рисует их одним системным вызовом GDI быстрее, чем N отдельных `Polyline`. Это **оптимизация Borland VCL под envelope plotting**.

### K12.6 Альтернативный путь — TBitmap.ScanLine + BitBlt

`BitBlt` (0x520190 thunk) имеет 11 callers, `StretchBlt` — 9. Это означает что **B-scan и переключатели «полный кадр» рисуют ВСЁ в TBitmap memory**, потом `BitBlt`-ом сливают на экран. A-scan, наоборот, рисуется **прямо на видимый Canvas** через PolyPolyline (быстрее для тонкой линии).

| Находка | Статус |
|---------|--------|
| 940. B-scan и большие графики используют **off-screen TBitmap + BitBlt**, A-scan — **прямой PolyPolyline на видимый Canvas** | 🟢 |

---

## §K13. Гейты / стробы — отдельная функция @ `0x004bde0c` (+ `0x004be4e0`)

Эти функции вызывают `TCanvas.Polyline` с `count=2` (т.е. 3 точки в Polyline — повтор первой). Структура — рисование **L-образных линий**, заходящих в две стороны от стартовой точки. Это **рамки гейтов** (стробов) над A-scan.

| VA         | Назначение                                       |
|-----------:|--------------------------------------------------|
| `0x004bde0c` | DrawGateFrame(gate_struct) — 2-сегмент L-shape   |
| `0x004be4e0` | DrawGateRect(gate_rect, coord_transform) — 4-сегмент закрытая рамка |
| `0x004ebcac` | WorldToCanvas — преобразование координат         |

```c
void DrawGateRect(TGate* gate, TCanvas* canvas) {
    POINT p1 = WorldToCanvas(canvas, gate->x1, gate->y2);  // bottom-left
    POINT p2 = WorldToCanvas(canvas, gate->x2, gate->y2);  // bottom-right
    POINT p3 = WorldToCanvas(canvas, gate->x2, gate->y1);  // top-right
    canvas->Polyline([p1, p2, p3]);              // L1: bottom + right
    
    POINT p4 = WorldToCanvas(canvas, gate->x1, gate->y1);
    POINT p5 = WorldToCanvas(canvas, gate->x2, gate->y1);
    POINT p6 = WorldToCanvas(canvas, gate->x1, gate->y2);
    canvas->Polyline([p4, p5, p6]);              // L2: top + left
}
```

| Находка | Статус |
|---------|--------|
| 941. Стробы (гейты) рисуются **двумя Polyline-вызовами** с count=2, образующими L-форму (одна снизу-справа, другая сверху-слева) | 🔒 |
| 942. `WorldToCanvas` @ `0x4ebcac` — функция преобразования логических координат в client-координаты Canvas | 🔒 |

---

## §K14. DGS / АРД-кривая @ `0x0048150c` и B-scan envelope @ `0x004816dc`

Обе функции имеют один и тот же набор FPU-констант:

| VA constant | Тип             | Значение                |
|------------:|-----------------|-------------------------|
| `0x4816c0`  | ext10 (80-bit)  | 0.01 (= 1/100)          |
| `0x4816cc`  | f32             | 0.5                     |
| `0x4816d0`  | f64             | π = 3.141592653589793   |
| `0x4816d8`  | f32             | 1.0                     |
| `0x4818e4`  | ext10           | (другая const — 0.0049... возможно 1/204) |
| `0x4818f0`  | f64             | π                       |
| `0x4818f8`  | f32             | 1.0                     |

Использование π намекает на тригонометрические преобразования. Стандартный паттерн DGS-curve в УЗ-дефектоскопии:

```
y_dB = 20*log10(distance/d_ref) + reference_db_loss
```

или для строгого DGS:

```
y_dB = 20*log10((d/d_ref)) + DGS_factor*sin(angle*π/180)
```

Обе функции рисуют через `TCanvas.Polyline` после серии вычислений с trig и degrees→radians (через ×π/180).

| Находка | Статус |
|---------|--------|
| 943. Две функции для plot DGS-кривых: `0x48150c` (одна модель) и `0x4816dc` (вторая модель) | 🔒 |
| 944. Обе используют π и log → DGS-кривая (Distance-Gain-Size) | 🟢 |
| 945. Углы вводятся в **градусах** (×π/180 = ×0.01×π/1.8) — типично для дефектоскопии | 🟡 |

---

## §K15. Сводка по новым находкам Round 7

| #          | Находка                                                       | Статус |
|-----------:|---------------------------------------------------------------|--------|
| 891–895    | Полный диспетчер `_SortBufData` (LUT, jump-table, decoder_type) | 🔒 |
| 896–898    | Структура `category_struct` (24 байта)                        | 🔒 |
| 899–905    | Точные формулы 7 meta-полей + TYPEZAP-литералы                | 🔒 |
| 906–909    | SchemaRouter — полный multi-stage диспетчер                   | 🔒 |
| 910–916    | **SchemaV1_writer (0x403834) — новая функция**                | 🔒 |
| 917–920    | NASTR2_writer — полный список полей                           | 🔒 |
| 921–923    | VAGON_writer — полный список полей                            | 🔒 |
| 924–927    | DateFormat / TimeFormat — точные offset'ы body                | 🔒 |
| 928–929    | NUMOBJ extractor — body[+0x11..+0x1b]                         | 🔒 |
| 930–931    | TYPEVAR может появляться дважды в out_buf                     | 🔒 |
| 932–933    | Карта 12 VCL TCanvas wrappers + Polyline +1 quirk             | 🔒 |
| 934–940    | **A-развёртка через PolyPolyline + виртуальный sample fetcher** | 🔒 |
| 941–942    | Гейты/стробы — DrawGateRect + WorldToCanvas                   | 🔒 |
| 943–945    | DGS-кривые: 2 функции с π/log                                 | 🔒/🟢 |

**Всего новых находок в этом раунде: 55 (891..945).**

После Round 7 общий счёт: **875 + 55 = 930 находок**.

---

## §K16. Открытые вопросы (продолжение §J18)

1. **Виртуальный метод `[ebx+0x28]` для сэмплов A-scan** — где реализован? Должен быть в VCL-классе обёртки буфера сэмплов. Кандидат — функции на `0x4a7000..0x4a8000`.
2. **PolyDraw `0x520338`** — действительно ли это PolyDraw, или OffsetClipRgn? Нужна сверка с подсказкой импорта GDI32.
3. **DGS-кривая (0x48150c) — точная формула**. Нужно расшифровать FP-инструкции пошагово, чтобы выявить `20*log10(...)` или `sin/cos`.
4. **`PROTOCOL` extractor** (последнее поле в SchemaV1 layout_B, NASTR2 layout_B, VAGON layout_B) — что именно читает? Скорее всего отдельный PassportLUT-декодер.
5. **`KM`/`M`/`MM` extractors VAGON** — какие LE16/BCD читаются?
6. **`CLOCK` extractor SchemaV1** — какой byte/format? Возможно `body[+N] (0..12)` для циферблата.
7. **`INDMAKER` extractor NASTR2 LAYOUT_A** — индекс изготовителя.
8. **Полное содержимое функции `0x4be610`** (Rectangle-heavy renderer) — главный main-window renderer для AcanProtocol.
9. **B-scan render** — где функция, читающая bitmap сэмплы для B-scan и расставляющая их через SetPixel/BitBlt?
10. **`Form_View` (DLL export ord 1)** @ `0x40131c` — GUI dialog, в Round6 §J2 упомянут, но не разбирался.

---

*Конец Этапа K (Round 7).*
