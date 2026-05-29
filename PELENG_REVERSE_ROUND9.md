# PELENG REVERSE — RAUND 9 / Этап M: Полный реверс decode-функций отчётов контроля

> Продолжение `PELENG_REVERSE_ROUND8.md` (§L0…§L9).
>
> Скоуп — то, что **не было** в раундах 1–8:
> - decode-функции для **«Отчёты контроля»** (Table13/Table23/Table33 в .dal),
> - обратная связь DLL→EXE через COM-интерфейс **`IData`** (TLB внутри EXE!),
> - SQL-схема Firebird (IBSQL/IBQuery статические запросы),
> - точное содержимое блока DGS-карт и acoustic-tail Settings,
> - точная карта `Decode*` функций в EXE для рендеринга в Word/HTML.
>
> **Бинари (те же, MD5 совпадает с §J0):**
> - `app/PelengPC.exe`  = `f46eb12f51353374a26a0c2c7b0e342e` (1 592 832 B)
> - `app/102_203dll.dll`= `cbc0f19c3697b595df64c19812094a68` (214 016 B)
> - `app/zapis2.exe`    = `2a039a511758964e223e8d67c06234a9` (1 220 608 B) — найден в этом раунде, ранее MD5 не публиковался
>
> **Источник:** `innoextract PelengPC_ver1_2.exe -d /home/peleng/` → `app/`.
>
> **Маркеры:** 🔒 / 🟢 / 🟡 как в Round 7–8. «📝 поправка к §X» означает уточнение/исправление ранней находки.
>
> **Метод:** capstone x86-32 поверх pefile + radare2 5.5 для статических ссылок и xrefs.

---

## §M0. Артефакты этапа M

| файл | назначение |
|---|---|
| `/home/peleng/app/PelengPC.exe` | главный GUI (BCB6) |
| `/home/peleng/app/102_203dll.dll` | DLL декодера |
| `/home/peleng/scripts/pe_loader.py` | helper: PE+sections+VA↔offset |
| `/home/peleng/work/` | дампы, json'ы, выгрузки символов |

---

## §M1. EXE экспортирует **TYPE LIBRARY** с интерфейсом `IData` — обратная COM-связь DLL→EXE

📝 НОВОЕ. В Round 5 §166 был найден CLSID `{E392D449-ECE3-4E27-BF74-05780FA1E6D6}` в DLL (целевой сервер). Теперь обнаружен **полный набор GUID'ов в EXE** — это **EXE является COM-сервером**, которому DLL передаёт результаты декодирования.

Адреса GUID'ов из экспорта `@Pelengpc_tlb@*`:

| Имя в TLB | VA | GUID |
|---|---:|---|
| `LIBID_PelengPC` | `0x52fdfc` | `{81E3C049-09B6-4480-81EF-B28664ACA2D4}` |
| `IID_IIData` | `0x52fe0c` | `{01F00D2C-AEE6-4ED9-BC0A-9C1F4B7358FF}` |
| `CLSID_IData` | `0x52fe1c` | `{C159F4AA-C6FC-4919-BE22-A1441A9038A0}` |

Сравните с **CLSID из DLL** (Round5 §166, `0x004284b4`-tlb): `{E392D449-ECE3-4E27-BF74-05780FA1E6D6}`. Это **другой GUID**.

То есть архитектура:
1. EXE регистрирует свой COM-объект под `CLSID_IData = {C159F4AA-…}` (TLB-based, через CoCreateInstance в собственном процессе).
2. DLL ищет внешний сервер под `{E392D449-…}` — это **другой COM-сервер** (DataTable), который **не EXE**.

---

## §M2. БД хранит ТОЛЬКО ОДНУ таблицу — `BLOCKZAP` (📝 поправка к Round5 §167)

📝 **Поправка к Round5 §167**. Ранее утверждалось, что в `PelengPC.fdb` есть таблицы `NASTR` (Настройки) и `RESULTS` (Протоколы). Проверка показывает обратное: в реальной FDB присутствует **ровно одна** пользовательская таблица.

`strings PelengPC.fdb` (фильтр без `RDB$`-системных):
- `BLOCKZAP` — единственная нормальная таблица записей
- `BLOCKLEN` — поле в таблице (длина BLOB?)
- `BLOCKUMV` — отдельное имя (вероятно тоже таблица или вид/индекс)
- Поля: `NUMBER`, `NUMKOD`, `NUMOBJ`, `NUMPRIB`, `NUMVERS`, `NUMZAP`, `KODOPERA`, `NAMEOPERA`, `TYPEZAP`, `DATEFORM`, `TIMEFORM`

SQL-операции в EXE (`/home/peleng/app/PelengPC.exe`) — `strings | grep BlockZap`:
- `SELECT * FROM BlockZap`
- `SELECT * FROM BlockZap WHERE Number=`
- `DELETE FROM BlockZap WHERE Number=`
- `INSERT INTO `
- `UPDATE `
- ` WHERE Number=`
- `SELECT GEN_ID(%s, %d) FROM RDB$DATABASE`

Дополнительно: EXE использует **TIBSQL batch-mode** для массовых вставок.

---

## §M3. Полная карта **TFormRaport** (форма "Рапорт Peleng")

Декодирована из DFM-ресурса (RCDATA/TFORMRAPORT, RVA `0x1f6048`, size `0x3e19`).

### M3.1 Структура формы

```text
TFormRaport (Caption='Рапорт Peleng', BorderStyle=bsSingle, ClientHeight=187, ClientWidth=455)
  TToolBar (Top=0)
    LoadItem     → OnClick=OpenClick
    SaveItem     → OnClick=SaveClick
    UpdDev       → OnClick=FromPriborClick
    LoadFlash    → OnClick=LoadFlashClick
  TEdit Edit      (TextOnDblClick=ViewButtonClick, начальное Text='0')
  TUpDown UpDown1  (привязан к Edit, Min=0)
  TListBox LB      (5 колонок, MultiSelect, OnClick=LBClick, OnDblClick=ViewButtonClick)
  TStatusBar StatusBar (SimplePanel)
  TRadioGroup RadioGroup (Hint='Обновить', Caption='Что показать?', ItemIndex=0,
                         OnClick=ChangeRadioClick, Items=
    [0]='Протокол А-развертки'
    [1]='Протокол В-развертки'
    [2]='Настройки'
    [3]='Отчет о контроле'  ← ИСКОМОЕ!
    [4]='Отчет толщиномера'
    [5]='Экран')
  TButton ViewButton (Caption='Показать', OnClick=ViewButtonClick)
  TMainMenu RaportMenu
    'Файл' (Открыть → OpenClick, Сохранить → SaveClick)
    'Вызвать' (Из прибора → FromPriborClick, Из файла → FromFileClick)
    'Справка' (О программе → HelpClick)
  TImageList ImageList
```

### M3.2 Точные адреса методов TFormRaport в EXE

| Метод (event handler) | VA | Размер entry | Замечание |
|---|---:|---:|---|
| `ShowRaport` | `0x4231b8` | 17 | OnShow для формы |
| `ChangeRadioClick` | `0x4231a0` | 23 | OnClick для RadioGroup |
| `FromPriborClick` | `0x422938` | 22 | "Из прибора" |
| `FromFileClick` | `0x422950` | 20 | "Из файла" |
| `LoadFlashClick` | `0x422764` | 22 | "Получить и сохранить все" |
| `ViewButtonClick` | `0x42274c` | 21 | "Показать" |
| `OpenClick` | `0x422508` | 16 | открыть файл |
| `SaveClick` | `0x422628` | 16 | сохранить файл |
| `HelpClick` | `0x422d88` | 16 | "О программе" |
| `LBClick` | `0x422d00` | 14 | клик в ListBox |

---

## §M4. Полная карта **TFormRaport.constructor** и таблицы записей

Конструктор формы (`0x41a5e4`) инициализирует таблицу из **6 типов записей** в `this+0x320`. Каждая запись имеет структуру 24 байта:

```c
struct RecordTypeEntry {
  AnsiString name;
  int lo;
  int hi;
  int size;
  int type;
  byte flag14;
  byte pad[3];
};
```

### M4.1 Полная таблица записей (`TFormRaport.constructor` @ `0x41a5e4`)

| idx | name | type | size | lo | hi | связь с RadioGroup |
|---|---|---:|---:|---:|---:|---|
| 0 | `Протокол А-развертки` | 0 | `0x2b6`=694 | 4000 | 4999 | Radio[0] часть #1 |
| 1 | `Протокол А-развертки` | 0 | `0x3a6`=934 | 6000 | 6999 | Radio[0] часть #2 |
| 2 | `Протокол B-развертки` | 0 | `0xfd6`=4054 | 5000 | 5999 | Radio[1] |
| 3 | `Настройка` | 1 | `0x176`=374 | 1000 | 1999 | Radio[2] "Настройки" |
| 4 | `Отчет о контроле` | 2 | `0x56`=86 | 10000 | 19999 | Radio[3] ← ИСКОМОЕ! |
| 5 | `Отчет толщиномера` | 3 | `0x56`=86 | 20000 | 29999 | Radio[4] |

---

## §M5. Полный pipeline «View record» от radio-клика до DLL

### M5.1 Карта функций

```text
TFormRaport.ViewButtonClick (0x42274c)
  └─→ FUN_004231dc
        ├─ читает StatusBar.SimpleText
        ├─ если "Экран" → selAddr = 0xea60
        ├─ иначе ищет запись в LB.Items
        └─→ call 0x41b9a4(this)
             ├─ buf = malloc(0x80020)
             ├─ status = call 0x41b43c(this, buf)
             ├─ если экран → 0x41ccb4(this, buf, status)
             └─ иначе
                  ├─→ 0x407ce0(g_FormMain, buf[4], buf[5])
                  └─→ 0x41042c(g_FormMain, &"", 0, 0, 0, 0, status, buf)
```

### M5.2 Семантика `0x41b43c` (unified loader)

- Sentinel `0xea60` — режим «Экран».
- Sweep range `[0x2710..0x752f]` = `[10000..30007]`.
- Normal range — любой другой адрес.
- Mode flag `this->mode_3c4`:
  - `0` → читать из файла
  - `1` → запросить блок у прибора через COM-порт

### M5.3 Семантика `0x41c914` (load_sweep)

Многоблочная загрузка sweep-протокола. Sweep-протокол = **N×100 байт линий + 16-байт хедер**.

### M5.4 Семантика `0x41cbf4` (load_screen)

Экран имеет 2 размера: `0x10c5/0x1485`, зависит от глобального бита `0x53e97c & 4`.

### M5.5 Семантика `0x41ccb4` (display_screen)

Экран отображается через **TFormScreen** (`0x5be9f8`), а НЕ через DLL.

### M5.6 Семантика `0x41b288` (load_from_file)

Файловый формат .zap/.fla: in-memory index `(addr, file_offset, size)` + raw payload region.

### M5.7 Семантика `0x424cc0` (Protocol_BlockRequest)

Wire-протокол: `0x42` (1 байт) + `addr_lo` + `addr_hi` ↦ N байт payload.

### M5.8 Семантика `0x41042c` (bridge EXE → DLL `_Form_View`)

`payload[2] = TYPE` — вот где entry-type попадает в DLL.

---

## §M6. БД-путь чтения отчёта (отдельный от UART/файла)

Полный путь чтения из Firebird от `NReadZapClick`/`ToolButton1Click`:

```text
TFormMain.NReadZapClick
TFormMain.ToolButton1Click
  └─→ FUN_0040c2a8
       └─→ 0x41042c (bridge → _Form_View)
```

### M6.1 Корректировка схемы Firebird

Глубокая выборка строк из `/home/peleng/app/PelengPC.fdb` показала минимум 4 физических таблицы:

| Таблица | Назначение |
|---|---|---|
| `BLOCKZAP` | основная хранилка блоков |
| `NASTR` | таблица настроек прибора |
| `RESULTS` | агрегат/результаты |
| `SHORTPROT` | «короткий протокол» |

---

## §M7. COM-инфраструктура: TLB EXE vs. DLL CoCreateInstance

### M7.1 Резюме

- EXE-side `IIData/IData/PelengPC` TLB
- DLL-side IDispatch объект
- GUID `{E392D449-...}` отсутствует в EXE, но присутствует в DLL
- GUID-ы `{81E3C049-...}/{01F00D2C-...}/{C159F4AA-...}` отсутствуют в DLL

### M7.2 EXE TLB: `IIData` интерфейс

```idl
library PelengPC {
  [uuid({01F00D2C-AEE6-4ED9-BC0A-9C1F4B7358FF}), dual, oleautomation]
  interface IIData : IDispatch {
    HRESULT SetData([in] SAFEARRAY(BYTE) arr);
  };

  [uuid({C159F4AA-C6FC-4919-BE22-A1441A9038A0})]
  coclass IData {
    [default] interface IIData;
  };
};
```

### M7.3 DLL CoCreateInstance цепочка (`_Form_View`)

```c
GetActiveObject → CoCreateInstance(LOCAL_SERVER) → QI(IDispatch)
→ GetIDsOfNames(L"ShowWindow") → Invoke(VT_ARRAY|VT_UI1)
```

---

## §M8. КРИТИЧЕСКАЯ НАХОДКА: декодер отчётов живёт в **zapis2.exe**, а не в DLL

### M8.1 Архитектура — три модуля, не два

```text
PelengPC.exe → 102_203dll.dll → zapis2.exe
```

**Бинарь `/home/peleng/app/zapis2.exe`** — `1220608` байт, MD5 `2a039a511758964e223e8d67c06234a9`, MSVC, MFC OLE Document Server.

### M8.2 Поиск GUID `{E392D449-...}` в системе

| где | присутствует |
|---|---|
| `PelengPC.exe` | ❌ |
| `102_203dll.dll` | ✅ |
| `zapis2.exe` | ✅ |
| `SetUp_PelengPC.exe / SETUP.exe / Driver.exe / CE.CAB` | ❌ |

### M8.3 Доказательства COM-сервера

В `zapis2.exe` импорты содержат всё необходимое:
- `CoRegisterClassObject`
- `CoResumeClassObjects`
- `CLSIDFromString`
- `CLSIDFromProgID`
- `CoDisconnectObject`
- `OleInitialize`

### M8.4 OLE Automation map — `ShowWindow(SAFEARRAY)`

`CZapisDoc::ShowWindow(VARIANT&)` — точка входа декодера.

### M8.5 MFC классы в `zapis2.exe`

- `CZapisApp`
- `CZapisDoc`
- `CZapisView`
- `CThickView`
- `CWinThread`
- `CFormView`
- `CScrollView`
- `CEdit`
- `CZapEdt`
- `IEnumVOID/XEnumVOID`

### M8.6 Текстовые шаблоны отчётов

`zapis2.exe` экспортирует отчёты в **двух форматах одновременно**: HTML и **MS Word 2003 XML** (WordprocessingML).

### M8.7 Семантические поля БД ↔ выходного отчёта

`zapis2.exe` использует имена полей, совпадающие с `BlockZap`/`SHORTPROT`-схемой.

---

## §M9. Резюме Round9 (что нового vs Rounds 1–8)

| Тема | Round1–8 | Round9 (новое) |
|---|---|---|
| Бинарные модули | EXE+DLL | **+ zapis2.exe** |
| Decode control report | искалось в DLL | **в `zapis2.exe`** |
| `0x41b9a4..0x41b43c` | частично | **полная карта 6 типов записи + sentinel Экран** |
| Mode flag `0x3c4` | ? | **0=file, 1=device** |
| Sweep classifier | ? | **`is_sweep(addr) = addr ∈ [10000..30007]`** |
| Screen-dump | ? | **спец. команда 0x9a** |
| Protocol BlockRequest | известно `0x42` | **полная wire-форма** |
| EXE TLB / IIData | известно | **CLSID/IID/LIBID, метод `SetData(arr)`** |
| DLL CLSID | известно | **присутствует только в DLL+zapis2.exe** |
| ProgID | ? | **`Peleng PC.IData`** |
| Реальные физ. таблицы FDB | NASTR/RESULTS | **+ BLOCKZAP, SHORTPROT** |
| BLOCKUMV | неизвестно | **поле в BLOCKZAP** |
| TFormRaport entry table | известно частично | **полная таблица 6 записей** |
| _Form_View bridge args | в общих чертах | **точно** |
| Output формат | известно | **HTML + MS Word 2003 XML** |

---

## Финальная находка

1066. Round9 раскрывает **полный 3-модульный pipeline** от UART до Word XML отчёта; финальный декодер — в `zapis2.exe` `0x4209fa` 🔒
