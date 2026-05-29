# Peleng Reverse — текущая карта decode-слоя

## Подтверждено

### `FUN_00408813(ctx, off)`
Главный extractor поля из body отчёта. Используется как чтение primitive-поля по смещению; дальше значение часто делится на 10 для получения класса/группы.

### `FUN_0040FF2B(ctx)`
Packed-state decoder. Использует биты из `ctx+0x190`:
- `bit0` — режим / override / variant
- `bits1..2` — subtype

Нормализация:
- `00 -> 4`
- `10 -> 2`
- `100 -> 5`
- `110 -> 3`

### `FUN_00411799(ctx)` и `FUN_00414704(ctx)`
Похожие packed-state декодеры, работающие с теми же report flags.

### `FUN_00413F6F(type, value)`
Рендерер строк по типу поля и значению; формирует человекочитаемое представление отчёта.

### `FUN_00414088(ctx)`
Не enum-дешифратор, а gate/presence check:
- true, если `ctx+0x106 != 0`

### `FUN_004136CF(ctx)`
Ещё один gate/presence check:
- использует `ctx+0x147` и `ctx+0xAF`

### `FUN_00413696(ctx)`
Gate/visibility check:
- использует `ctx+0x147`, `ctx+0x106`, `ctx+0x137 & 4`

---

## Descriptor / FIELD_DESC слой

Повторяется таблица описателей:

- `offset`
- `field_type`
- `caption`
- `callback`

Типы:
- `0x04` — 16-битное значение
- `0x0D` — 8-битное значение
- `0x3E` — комплексное поле: `LE16 + BYTE + callback`

Примеры:
- `0x5E / type 4 / ifLength`
- `0x60 / type 0x0D / ifHight`
- `0x7E / type 0x3E / defekt_edit`

---

## Контроль 10..19

### Наблюдения
- `0x7E` обрабатывается через `FUN_00408813(ctx, 0x7E)`.
- Дальше значение часто нормализуется через деление на 10.
- Это похоже на классификатор/код группы, а не на обычный счётчик.

### Вероятная структура
- часть полей — `LE16`
- часть — `BYTE`
- часть — packed bitfields
- часть — классификаторы с `raw/10`

### Группы полей, которые ещё нужно добить
- `Сторона`
- `Шейка`
- `Обод`
- `Обточка`
- `Гребень`

---

## Рабочая гипотеза структуры

```c
struct CONTROL_REPORT {
    uint16 datePacked;
    uint8  objectType;
    uint16 objectNo;
    uint16 melting;
    uint16 factory;
    uint8  year;
    uint8  wheelBitmap;
    uint8  constructPacked;
    uint16 neckRaw;
    uint16 rimRaw;
    uint16 defectRaw;
    uint8  defectSubtype;
};
```

Это рабочая карта, не финальная истина.

---

## Что уже не подтверждается

- `FUN_00414088` — не enum-декадёр, а presence/gate
- `FUN_004136CF` — не enum-декадёр, а presence/gate
- `FUN_00413696` — не enum-декадёр, а visibility/gate

---

## Следующий шаг

Добирать функции вокруг:
- `FUN_00408813`
- `FUN_0040FF2B`
- `FUN_00411799`
- `FUN_00414704`
- `FUN_00413F6F`

и привязывать их к конкретным `FIELD_DESC`-описателям.
