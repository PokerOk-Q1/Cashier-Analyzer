#!/usr/bin/env python3
"""
Анализ финансовой истории из кассы покер-рума PokerOK.
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict, OrderedDict
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Попробуем подключить pandas, но скрипт должен работать и без него
try:
    import pandas as pd  # type: ignore

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# ====== CLI PARSING ======

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Анализ кассы покер-рума (cashier report)."
    )
    parser.add_argument(
        "-f", "--file",
        required=True,
        help="Путь к файлу кассы (.csv или .xlsx)."
    )
    parser.add_argument(
        "--map-config",
        help="Путь к JSON-файлу с маппингом колонок (date, type, amount, currency, description)."
    )
    parser.add_argument(
        "--currency",
        help="Фильтр по валюте (например, USD)."
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        help="Начальная дата периода (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        help="Конечная дата периода (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--monthly",
        action="store_true",
        help="Вывод помесячной статистики."
    )
    parser.add_argument(
        "--by-type",
        action="store_true",
        help="Вывод разбивки по типам транзакций."
    )
    parser.add_argument(
        "--export",
        help="Путь к CSV-файлу для экспорта отчёта."
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Отключить цветной вывод."
    )
    parser.add_argument(
        "--show-unknown",
        action="store_true",
        help="Показать количество/сумму транзакций с типом 'unknown'."
    )
    return parser.parse_args()


# ====== ВСПОМОГАТЕЛЬНЫЕ ШТУКИ ======

def supports_color(no_color_flag: bool) -> bool:
    return (not no_color_flag) and sys.stdout.isatty()


def colorize(text: str, color_code: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"\033[{color_code}m{text}\033[0m"


def load_mapping(path: Optional[str]) -> Dict[str, str]:
    """
    Возвращает mapping логических полей -> имена колонок в файле.
    Если path=None, ожидается, что колонки уже имеют имена 'date', 'type', 'amount', 'currency', 'description'.
    """
    default_mapping = {
        "date": "date",
        "type": "type",
        "amount": "amount",
        "currency": "currency",
        "description": "description",
    }
    if not path:
        return default_mapping

    try:
        with open(path, "r", encoding="utf-8") as f:
            user_map = json.load(f)
        mapping = default_mapping.copy()
        mapping.update(user_map)
        return mapping
    except Exception as e:
        print(f"Ошибка чтения файла маппинга '{path}': {e}", file=sys.stderr)
        sys.exit(1)


def try_parse_date(value: str) -> Optional[datetime]:
    """
    Пытается распарсить строку даты в datetime с набором популярных форматів.
    Возвращает None, если не получилось.
    """
    if not value:
        return None
    value = value.strip()
    # Возможные форматы (можно расширять)
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # Попробуем fromisoformat
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def parse_date_arg(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    dt = try_parse_date(value)
    if not dt:
        print(f"Неверный формат даты аргумента: '{value}' (ожидается YYYY-MM-DD)", file=sys.stderr)
        sys.exit(1)
    return dt.date()


def parse_amount(value: str) -> Optional[float]:
    """
    Парсинг числовых значений:
    - убираем пробелы
    - пытаемся адекватно обработать запятые/точки.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # убираем пробелы (вдруг разделители тысяч)
    s = s.replace(" ", "")
    # если только запятая и нет точки -> считаем её разделителем дробной части
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    # если и запятая, и точка: уберём запятые как разделители тысяч
    elif "," in s and "." in s:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


# ====== ЧТЕНИЕ ФАЙЛОВ ======

def read_csv_file(path: str, mapping: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Чтение CSV без pandas.
    """
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                header = reader.fieldnames or []
                # Проверим наличие колонок
                check_required_columns(header, mapping)
                rows = [row for row in reader]
                return rows
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            print(f"Файл не найден: {path}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Ошибка чтения CSV '{path}': {e}", file=sys.stderr)
            sys.exit(1)
    print(f"Не удалось определить кодировку файла: {path}", file=sys.stderr)
    sys.exit(1)


def read_xlsx_file(path: str, mapping: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Чтение XLSX только через pandas.
    """
    if not HAS_PANDAS:
        print("Файл .xlsx поддерживается только при наличии pandas. Установите pandas или используйте CSV.", file=sys.stderr)
        sys.exit(1)
    try:
        df = pd.read_excel(path)
    except FileNotFoundError:
        print(f"Файл не найден: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка чтения XLSX '{path}': {e}", file=sys.stderr)
        sys.exit(1)

    header = list(df.columns)
    check_required_columns(header, mapping)

    records: List[Dict[str, Any]] = df.to_dict(orient="records")  # type: ignore
    return records


def check_required_columns(header: List[str], mapping: Dict[str, str]) -> None:
    required_logical = ["date", "type", "amount", "currency"]
    missing = []
    for logical in required_logical:
        col = mapping.get(logical)
        if col not in header:
            missing.append(f"{logical} -> '{col}'")
    if missing:
        print("В файле отсутствуют обязательные колонки:", file=sys.stderr)
        for m in missing:
            print("  ", m, file=sys.stderr)
        sys.exit(1)


# ====== НОРМАЛИЗАЦИЯ ТРАНЗАКЦИЙ ======

def normalize_type(raw_type: str) -> str:
    """
    Приводим сырой тип (как в отчёте рума) к одному из:
    deposit, withdrawal, buyin, payout, rakeback, bonus, fee, unknown
    """
    if raw_type is None:
        return "unknown"
    t = str(raw_type).strip().lower()

    # Примеры маппинга (можно адаптировать под конкретный формат ПокерОк)
    if "deposit" in t or "top up" in t or "cashin" in t:
        return "deposit"
    if "withdraw" in t or "cashout" in t or "payout to" in t:
        return "withdrawal"
    if "buy-in" in t or "buyin" in t or "entry" in t or "registration" in t:
        return "buyin"
    if "winnings" in t or "payout" in t or "prize" in t or "cash game winnings" in t:
        return "payout"
    if "rakeback" in t or "fish buffet" in t or "cashback" in t:
        return "rakeback"
    if "bonus" in t or "reward" in t or "promo" in t:
        return "bonus"
    if "fee" in t or "commission" in t:
        return "fee"

    return "unknown"


def normalize_rows(raw_rows: List[Dict[str, Any]],
                   mapping: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Приводим сырые строки к единому виду:
    {
        "date": datetime,
        "type": "deposit"/...,
        "amount": float (абсолютное значение),
        "currency": str,
        "description": str,
        "raw_type": str
    }

    ВАЖНО: amount интерпретируется как абсолютная величина,
    знак операции определяется по type.
    """
    normalized: List[Dict[str, Any]] = []
    skipped = 0

    for idx, row in enumerate(raw_rows, start=1):
        try:
            raw_date = row.get(mapping["date"])
            raw_type = row.get(mapping["type"])
            raw_amount = row.get(mapping["amount"])
            raw_currency = row.get(mapping["currency"])
            raw_desc = row.get(mapping.get("description", ""), "")

            dt = try_parse_date(str(raw_date)) if raw_date is not None else None
            amount = parse_amount(str(raw_amount)) if raw_amount is not None else None
            currency = str(raw_currency).strip().upper() if raw_currency is not None else ""
            desc = "" if raw_desc is None else str(raw_desc)

            if not dt or amount is None or not currency:
                skipped += 1
                continue

            ntype = normalize_type(str(raw_type))

            normalized.append({
                "date": dt,
                "type": ntype,
                "amount": abs(amount),  # абсолют
                "currency": currency,
                "description": desc,
                "raw_type": raw_type,
            })
        except Exception:
            skipped += 1
            continue

    if skipped > 0:
        print(f"WARNING: пропущено строк: {skipped} (ошибка парсинга даты/суммы/валюты)", file=sys.stderr)

    return normalized


def filter_data(rows: List[Dict[str, Any]],
                from_d: Optional[date],
                to_d: Optional[date],
                currency: Optional[str]) -> List[Dict[str, Any]]:
    res: List[Dict[str, Any]] = []
    if currency:
        currency = currency.upper()

    to_d_end: Optional[datetime] = None
    if to_d:
        to_d_end = datetime.combine(to_d + timedelta(days=1), datetime.min.time())

    for row in rows:
        dt: datetime = row["date"]
        cur: str = row["currency"]

        if from_d:
            if dt < datetime.combine(from_d, datetime.min.time()):
                continue
        if to_d_end:
            if dt >= to_d_end:
                continue
        if currency and cur != currency:
            continue

        res.append(row)
    return res


# ====== РАСЧЁТ МЕТРИК ======

def calculate_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Считаем агрегаты по одному набору строк (одна валюта).
    Все amount здесь абсолютные значения.
    """
    totals = {
        "deposit": 0.0,
        "withdrawal": 0.0,
        "buyin": 0.0,
        "payout": 0.0,
        "rakeback": 0.0,
        "bonus": 0.0,
        "fee": 0.0,
        "unknown": 0.0,
    }

    for row in rows:
        t = row["type"]
        amt = float(row["amount"])
        if t in totals:
            totals[t] += amt
        else:
            totals["unknown"] += amt

    deposits = totals["deposit"]
    withdrawals = totals["withdrawal"]
    buyins = totals["buyin"]
    payouts = totals["payout"]
    rakeback = totals["rakeback"]
    bonus = totals["bonus"]
    fee = totals["fee"]
    unknown = totals["unknown"]

    net_cashflow = deposits - withdrawals
    game_result = payouts - buyins
    total_profit = game_result + rakeback + bonus
    effective = total_profit - fee

    summary = {
        "deposits": deposits,
        "withdrawals": withdrawals,
        "buyins": buyins,
        "payouts": payouts,
        "rakeback": rakeback,
        "bonus": bonus,
        "fee": fee,
        "unknown": unknown,
        "net_cashflow": net_cashflow,
        "game_result": game_result,
        "total_profit": total_profit,
        "effective": effective,
    }
    return summary


def calculate_monthly_stats(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Помесячная статистика.
    Для каждого месяца считаем:
    - Net (deposits - withdrawals)
    - Game (payouts - buyins)
    - Rakeback
    - Bonus
    - Total = Game + Rakeback + Bonus
    """
    # Соберём по месяцам все строки
    by_month: Dict[Tuple[int, int], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        dt: datetime = row["date"]
        key = (dt.year, dt.month)
        by_month[key].append(row)

    # Отсортируем по дате
    ordered_keys = sorted(by_month.keys())
    result: List[Dict[str, Any]] = []

    for year, month in ordered_keys:
        subrows = by_month[(year, month)]
        summ = calculate_summary(subrows)
        result.append({
            "year": year,
            "month": month,
            "net": summ["net_cashflow"],
            "game": summ["game_result"],
            "rakeback": summ["rakeback"],
            "bonus": summ["bonus"],
            "total": summ["total_profit"],
        })

    return result


def calculate_by_type(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Суммы по типам для вывода "BY TYPE".
    Знак подбираем интуитивно:
    - deposit, payout, rakeback, bonus: +
    - withdrawal, buyin, fee: -
    """
    type_sums: Dict[str, float] = defaultdict(float)

    for row in rows:
        t = row["type"]
        amt = float(row["amount"])
        if t in ("withdrawal", "buyin", "fee"):
            signed = -amt
        elif t in ("deposit", "payout", "rakeback", "bonus"):
            signed = amt
        else:
            # unknown оставим как 0 (можно поменять логику при желании)
            signed = 0.0
        type_sums[t] += signed

    return dict(type_sums)


# ====== ВЫВОД ======

def format_money(value: float) -> str:
    return f"{value:+.2f}"


def print_summary(summary: Dict[str, Any],
                  currency: str,
                  date_range: Tuple[Optional[date], Optional[date]],
                  use_color: bool) -> None:
    from_d, to_d = date_range
    period_str = []
    if from_d:
        period_str.append(from_d.isoformat())
    if to_d:
        period_str.append(to_d.isoformat())
    period_text = " .. ".join(period_str) if period_str else "все доступные данные"

    print("=== CASHIER SUMMARY ===")
    print(f"Период: {period_text}")
    print(f"Валюта: {currency}")
    print()

    def line(label: str, val: float, positive_color: str = "32", negative_color: str = "31"):
        s = format_money(val)
        color_code = positive_color if val >= 0 else negative_color
        s_colored = colorize(s, color_code, use_color)
        print(f"{label:<15} {s_colored}")

    line("Депозиты:", summary["deposits"])
    line("Выводы:", -summary["withdrawals"])  # отображаем как -X
    line("Net cashflow:", summary["net_cashflow"])
    print()
    line("Buy-ins:", -summary["buyins"])
    line("Payouts:", summary["payouts"])
    line("Game result:", summary["game_result"])
    print()
    line("Rakeback:", summary["rakeback"])
    line("Bonuses:", summary["bonus"])
    line("Fees:", -summary["fee"])
    print("-" * 28)
    line("Total profit:", summary["total_profit"])
    line("Effective:", summary["effective"])
    print()


def print_monthly_stats(monthly: List[Dict[str, Any]],
                        use_color: bool) -> None:
    if not monthly:
        print("Нет данных для помесячной статистики.")
        return

    print("=== MONTHLY STATS ===")
    header = f"{'Month':<8} {'Net':>12} {'Game':>12} {'Rakeback':>12} {'Bonus':>12} {'Total':>12}"
    print(header)
    print("-" * len(header))

    for row in monthly:
        month_str = f"{row['year']}-{row['month']:02d}"
        net = format_money(row["net"])
        game = format_money(row["game"])
        rakeback = format_money(row["rakeback"])
        bonus = format_money(row["bonus"])
        total = format_money(row["total"])

        # слегка раскрасим Total
        total_colored = colorize(
            total,
            "32" if row["total"] >= 0 else "31",
            use_color
        )

        print(f"{month_str:<8} {net:>12} {game:>12} {rakeback:>12} {bonus:>12} {total_colored:>12}")
    print()


def print_by_type(type_stats: Dict[str, float],
                  use_color: bool) -> None:
    if not type_stats:
        print("Нет данных для разбивки по типам.")
        return

    print("=== BY TYPE ===")
    print(f"{'Type':<12} {'Amount':>12}")
    print("-" * 25)
    for t in sorted(type_stats.keys()):
        val = type_stats[t]
        s = format_money(val)
        s_colored = colorize(
            s,
            "32" if val >= 0 else "31",
            use_color
        )
        print(f"{t:<12} {s_colored:>12}")
    print()


def export_report(path: str,
                  currency: str,
                  date_range: Tuple[Optional[date], Optional[date]],
                  summary: Dict[str, Any],
                  monthly: Optional[List[Dict[str, Any]]] = None) -> None:
    """
    Экспорт в CSV.
    Если monthly не None -> экспортируем помесячную статистику.
    Иначе -> одну строку общей сводки.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    except Exception:
        # если папки нет и не можем создать — пусть упадёт при записи
        pass

    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if monthly is not None:
                writer.writerow([
                    "currency", "year", "month",
                    "net", "game", "rakeback", "bonus", "total"
                ])
                for row in monthly:
                    writer.writerow([
                        currency,
                        row["year"],
                        row["month"],
                        f"{row['net']:.2f}",
                        f"{row['game']:.2f}",
                        f"{row['rakeback']:.2f}",
                        f"{row['bonus']:.2f}",
                        f"{row['total']:.2f}",
                    ])
            else:
                from_d, to_d = date_range
                writer.writerow([
                    "currency", "from", "to",
                    "deposits", "withdrawals",
                    "net_cashflow",
                    "buyins", "payouts", "game_result",
                    "rakeback", "bonus", "fee",
                    "total_profit", "effective",
                ])
                writer.writerow([
                    currency,
                    from_d.isoformat() if from_d else "",
                    to_d.isoformat() if to_d else "",
                    f"{summary['deposits']:.2f}",
                    f"{summary['withdrawals']:.2f}",
                    f"{summary['net_cashflow']:.2f}",
                    f"{summary['buyins']:.2f}",
                    f"{summary['payouts']:.2f}",
                    f"{summary['game_result']:.2f}",
                    f"{summary['rakeback']:.2f}",
                    f"{summary['bonus']:.2f}",
                    f"{summary['fee']:.2f}",
                    f"{summary['total_profit']:.2f}",
                    f"{summary['effective']:.2f}",
                ])
        print(f"Отчёт экспортирован в: {path}")
    except Exception as e:
        print(f"Ошибка экспорта отчёта в '{path}': {e}", file=sys.stderr)


# ====== MAIN ======

def main() -> None:
    args = parse_args()
    use_color = supports_color(args.no_color)

    mapping = load_mapping(args.map_config)

    ext = os.path.splitext(args.file)[1].lower()
    if ext == ".csv":
        raw_rows = read_csv_file(args.file, mapping)
    elif ext in (".xls", ".xlsx"):
        raw_rows = read_xlsx_file(args.file, mapping)
    else:
        print("Поддерживаются только файлы .csv и .xlsx", file=sys.stderr)
        sys.exit(1)

    normalized = normalize_rows(raw_rows, mapping)

    if not normalized:
        print("Не удалось распарсить ни одной строки. Проверьте формат файла/маппинг.", file=sys.stderr)
        sys.exit(1)

    from_d = parse_date_arg(args.from_date)
    to_d = parse_date_arg(args.to_date)
    currency_filter = args.currency.upper() if args.currency else None

    filtered = filter_data(normalized, from_d, to_d, currency_filter)

    if not filtered:
        print("После фильтрации по датам/валюте не осталось ни одной строки.")
        sys.exit(0)

    # Определим, какие валюты остались
    currencies = sorted({row["currency"] for row in filtered})

    if len(currencies) > 1 and not currency_filter:
        print("WARNING: обнаружено несколько валют, будет отчёт по каждой отдельно:", ", ".join(currencies))

    # Для экспорта: если несколько валют без фильтра и указан --export,
    # мы добавим суффикс к имени файла вида _USD, _EUR и т.д.
    base_export_path = args.export
    export_per_currency = len(currencies) > 1 and base_export_path is not None and currency_filter is None

    for cur in currencies:
        rows_cur = [r for r in filtered if r["currency"] == cur]

        # Определим диапазон дат по фактическим данным, если не задано явно
        if rows_cur:
            min_dt = min(r["date"] for r in rows_cur).date()
            max_dt = max(r["date"] for r in rows_cur).date()
        else:
            min_dt = from_d
            max_dt = to_d

        date_range = (from_d or min_dt, to_d or max_dt)

        summary = calculate_summary(rows_cur)
        print_summary(summary, cur, date_range, use_color)

        if args.monthly:
            monthly = calculate_monthly_stats(rows_cur)
            print_monthly_stats(monthly, use_color)
        else:
            monthly = None

        if args.by_type:
            type_stats = calculate_by_type(rows_cur)
            print_by_type(type_stats, use_color)

        if args.show_unknown and summary["unknown"] > 0:
            print(f"UNKNOWN: сумма транзакций с неопознанным типом: {summary['unknown']:.2f}")
            print()

        if base_export_path:
            if export_per_currency:
                root, ext2 = os.path.splitext(base_export_path)
                export_path = f"{root}_{cur}{ext2 or '.csv'}"
            else:
                export_path = base_export_path

            export_report(export_path, cur, date_range, summary, monthly)

    # конец main()


if __name__ == "__main__":
    main()