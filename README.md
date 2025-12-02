# Скрипт анализа транзакций кассы на ПокерОк

Анализатор истории кассы покер-рума ПокерОк в формате CSV/XLSX. Скрипт `cashier.py` читает выгрузку из кассы (cashier report), нормализует данные и строит удобные отчёты:

- общий итог по депозитам / выводам / игре / рейкбеку / бонусам / комиссиям;
- помесячная статистика;
- разбивка по типам транзакций;
- экспорт отчёта в CSV.

---

## Возможности

- Поддержка файлов **CSV** (обязательно) и **XLSX** (если установлен `pandas`).
- Нормализация типов транзакций:
  - `deposit` — депозиты;
  - `withdrawal` — выводы;
  - `buyin` — бай-ины (турниры/кэш);
  - `payout` — выплаты/призы;
  - `rakeback` — рейкбек/кэшбэк/промо;
  - `bonus` — бонусы/награды;
  - `fee` — комиссии;
  - `unknown` — всё, что не распознано.
- Фильтрация:
  - по периоду (`--from`, `--to`);
  - по валюте (`--currency`).
- Расчёт:
  - **Net cashflow** — депозиты минус выводы;
  - **Game result** — выплаты минус бай-ины;
  - **Total profit** — результат игры + рейкбек + бонусы;
  - **Effective** — итог с учётом комиссий.
- Помесячная агрегация (`--monthly`).
- Разбивка по типам транзакций (`--by-type`).
- Поддержка нескольких валют (отдельный отчёт по каждой).
- Экспорт отчёта в CSV (`--export`).
- Работа с маппингом колонок через JSON (`--map-config`).

---

## Установка

1. Клонировать репозиторий:

```bash
git clone https://github.com/PokerOk-Q1/Cashier-Analyzer.git
cd Cashier-Analyzer
```

2. Установить Python 3.9+ (если ещё не установлен).

3. (Опционально) установить зависимости для работы с XLSX:

```bash
pip install pandas openpyxl
```

Если `pandas` не установлен, скрипт всё равно будет работать, но только с CSV-файлами.

---

## Входные данные

### Поддерживаемые форматы

* **CSV** — обязательная поддержка;
* **XLSX** — при наличии `pandas`.

### Логические поля

Скрипт внутри оперирует логическими полями:

* `date` — дата/время транзакции;
* `type` — тип операции (строка);
* `amount` — сумма операции;
* `currency` — валюта (`USD`, `EUR`, `RUB`, и т.д.);
* `description` — дополнительное описание (опционально).

По умолчанию ожидается, что в файле есть колонки с именами:

```text
date, type, amount, currency, description
```

Если в реальном отчёте имена другие (например, `Transaction Time`, `Amount`, `Currency`, и т.п.), используется маппинг через JSON.

---

## Маппинг колонок (`--map-config`)

Для гибкой настройки соответствия колонок можно указать JSON-файл маппинга:

```json
{
  "date": "Transaction Time",
  "type": "Type",
  "amount": "Amount",
  "currency": "Currency",
  "description": "Details"
}
```

* Ключи слева (`date`, `type`, `amount`, `currency`, `description`) — логические поля скрипта.
* Значения справа — реальные названия колонок в файле кассы.

Пример использования:

```bash
python cashier.py -f data/pokerok_cashier.csv --map-config config/mapping.json
```

Если `--map-config` не указан, скрипт ожидает, что в файле уже есть колонки с именами `date`, `type`, `amount`, `currency` (и опционально `description`).

---

## Типы транзакций и нормализация

`cashier.py` приводит сырой тип транзакции к одному из внутренних:

* `deposit` — депозиты (примерные исходные значения: `Deposit`, `Top Up`, `Cash In` и т.п.);
* `withdrawal` — вывод средств (`Withdraw`, `Cashout`, `Payout to ...`);
* `buyin` — бай-ины (`Tournament Buy-In`, `Cash Game Buy-In`, `Entry`, `Registration`);
* `payout` — выплаты/призы (`Winnings`, `Payout`, `Prize`, `Cash Game Winnings`);
* `rakeback` — рейкбек / кэшбэк (`Rakeback`, `Fish Buffet`, `Cashback`);
* `bonus` — бонусы/награды (`Bonus`, `Reward`, `Promo`);
* `fee` — комиссии (`Fee`, `Commission`);
* `unknown` — всё, что не попадает ни в одну категорию.

Логика маппинга реализована в коде и может быть при необходимости расширена под конкретный формат отчёта.

---

## Использование

Общий формат:

```bash
python cashier.py --file path/to/file.csv [OPTIONS]
```

или короткая форма:

```bash
python cashier.py -f path/to/file.csv [OPTIONS]
```

### Основные аргументы

* `-f, --file` — **обязательно**, путь к файлу кассы (`.csv` или `.xlsx`);
* `--map-config` — путь к JSON с маппингом колонок;
* `--currency` — фильтр по валюте (например, `USD`);
* `--from` — начальная дата периода анализа (`YYYY-MM-DD`);
* `--to` — конечная дата периода анализа (`YYYY-MM-DD`);
* `--monthly` — вывод помесячной статистики;
* `--by-type` — вывод разбивки по типу транзакции;
* `--export` — путь к CSV для экспорта отчёта;
* `--no-color` — отключить цветной вывод в консоль;
* `--show-unknown` — вывести сумму транзакций с типом `unknown`.

---

## Примеры запуска

### 1. Базовый отчёт по всему периоду

```bash
python cashier.py -f data/pokerok_cashier.csv
```

Выведет общую сводку по всем транзакциям в файле.

---

### 2. Анализ за конкретный период

```bash
python cashier.py -f data/pokerok_cashier.csv --from 2024-01-01 --to 2024-12-31
```

Анализ только транзакций за 2024 год.

---

### 3. Анализ по конкретной валюте

```bash
python cashier.py -f data/pokerok_cashier.csv --currency USD
```

Будут учтены только строки с валютой `USD`.

---

### 4. Помесячная статистика

```bash
python cashier.py -f data/pokerok_cashier.csv --monthly
```

Помимо общей сводки, выведет таблицу по месяцам:

```text
=== MONTHLY STATS ===
Month       Net        Game    Rakeback       Bonus       Total
2024-01   +50.00     +20.00      +5.00       +0.00      +75.00
2024-02   -30.00     +80.00     +10.00       +0.00      +60.00
...
```

---

### 5. Разбивка по типам транзакций

```bash
python cashier.py -f data/pokerok_cashier.csv --by-type
```

Выведет суммарные значения по каждому типу:

```text
=== BY TYPE ===
Type           Amount
bonus         +25.00
buyin        -800.00
deposit     +1500.00
fee          -10.00
payout       +950.00
rakeback      +75.00
withdrawal -1200.00
```

---

### 6. Экспорт отчёта в CSV

```bash
python cashier.py -f data/pokerok_cashier.csv --from 2024-01-01 --to 2024-12-31 --monthly --export reports/report_2024.csv
```

* Если указан `--monthly`, экспортируется помесячная статистика.
* Если `--monthly` **не указан**, экспортируется одна строка общей сводки.

При наличии нескольких валют без фильтра `--currency` отчёт будет создан по каждой валюте отдельно.
Например, при `--export reports/report.csv` будут сформированы файлы:

* `reports/report_USD.csv`
* `reports/report_EUR.csv`
* и т.д.

---

## Интерпретация результатов

### Общая сводка

Пример вывода:

```text
=== CASHIER SUMMARY ===
Период: 2024-01-01 .. 2024-12-31
Валюта: USD

Депозиты:       +1500.00
Выводы:         -1200.00
Net cashflow:   +300.00

Buy-ins:        -800.00
Payouts:        +950.00
Game result:    +150.00

Rakeback:       +75.00
Bonuses:        +25.00
Fees:           -10.00
----------------------------
Total profit:   +250.00
Effective:      +240.00
```

* **Net cashflow** — сколько денег фактически введено в рум (депозиты минус выводы).
* **Game result** — результат чисто по игре (плюс/минус без рейкбека и бонусов).
* **Total profit** — игра + рейкбек + бонусы.
* **Effective** — Total profit с учётом комиссий (`fee`).

### Unknown-транзакции

Если есть строки с типом `unknown`, можно вывести их суммарную величину:

```bash
python cashier.py -f data/pokerok_cashier.csv --show-unknown
```

Пример:

```text
UNKNOWN: сумма транзакций с неопознанным типом: 12.34
```

Это сигнал посмотреть, нет ли в отчёте нового неизвестного типа операций, который стоит добавить в логику нормализации.

---

## Примеры структуры данных

### Пример CSV (`examples/cashier_sample.csv`)

```csv
date,type,amount,currency,description
2024-01-01 12:00:00,Deposit,100,USD,Deposit via card
2024-01-01 13:00:00,Tournament Buy-In,10,USD,Daily Main Event
2024-01-01 16:30:00,Tournament Winnings,25,USD,Daily Main Event
2024-01-02 18:20:00,Fish Buffet,2.5,USD,Rakeback
2024-01-03 20:00:00,Withdraw,50,USD,Cashout
2024-01-04 21:15:00,Fee,1,USD,Service fee
```

## Лицензия

Проект распространяется по лицензии **MIT**. Подробнее см. файл [`LICENSE`](./LICENSE).
