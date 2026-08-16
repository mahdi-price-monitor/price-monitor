import csv
import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE_URL = "https://www.tgju.org/profile/price_dollar_rl"
SOURCE = "tgju"
SYMBOL = "usd"
HISTORY_FILE = "data/tgju_history.csv"
LATEST_FILE = "data/tgju_latest.json"


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_row = False
        self.in_cell = False
        self.rows = []
        self.current_row = []
        self.current_cell = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            text = " ".join("".join(self.current_cell).split())
            self.current_row.append(text)
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_row = False

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)


def normalize_digits(value):
    if value is None:
        return ""
    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )
    return value.translate(table)


def clean_value(value):
    value = normalize_digits(value)
    value = value.replace(",", "").replace("٬", "").strip()
    value = value.replace("−", "-").replace("٪", "%")
    return value


def to_number(value):
    value = clean_value(value).replace("%", "")
    if value in ("", "-", "—"):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except ValueError:
        return None


def fetch_page():
    request = Request(
        BASE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; price-monitor/1.0)"
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_market_snapshot(html):
    parser = TableParser()
    parser.feed(html)

    fields = {}
    wanted = {
        "نرخ فعلی": "last_price",
        "نرخ روز گذشته": "yesterday_price",
        "میزان تغییر نسبت به روز گذشته": "price_change",
        "درصد تغییر نسبت به روز گذشته": "price_change_percent",
        "زمان ثبت آخرین نرخ": "last_update",
    }

    for row in parser.rows:
        if len(row) < 2:
            continue
        label = row[0].strip()
        for key, field in wanted.items():
            if label == key or label.startswith(key):
                fields[field] = clean_value(row[1])

    if "last_price" not in fields:
        raise RuntimeError("TGJU dollar page: current price was not found.")

    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc.astimezone(ZoneInfo("Asia/Tehran"))

    return {
        "collected_at_utc": now_utc.isoformat(),
        "collected_at_tehran": now_tehran.isoformat(),
        "source": SOURCE,
        "symbol": SYMBOL,
        "market": "free",
        "last_price": to_number(fields.get("last_price")),
        "yesterday_price": to_number(fields.get("yesterday_price")),
        "price_change": to_number(fields.get("price_change")),
        "price_change_percent": to_number(fields.get("price_change_percent")),
        "source_last_update": fields.get("last_update", ""),
        "source_url": BASE_URL,
    }


def append_if_changed(record):
    os.makedirs("data", exist_ok=True)
    fields = list(record.keys())
    rows = []

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", newline="", encoding="utf-8-sig") as file:
            rows = list(csv.DictReader(file))

    if rows:
        last = rows[-1]
        comparable = ["last_price", "yesterday_price", "price_change", "price_change_percent"]
        if all(str(last.get(k, "")) == str(record.get(k, "")) for k in comparable):
            print("TGJU dollar data has not changed. No new history row added.")
            return False

    file_exists = os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)

    return True


def main():
    html = fetch_page()
    record = extract_market_snapshot(html)

    os.makedirs("data", exist_ok=True)
    with open(LATEST_FILE, "w", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)

    changed = append_if_changed(record)
    print(json.dumps({"changed": changed, "record": record}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
