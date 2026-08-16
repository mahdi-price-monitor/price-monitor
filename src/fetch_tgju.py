import csv
import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from html import unescape
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

SOURCE = "tgju"
HISTORY_FILE = "data/tgju_market_history.csv"
LATEST_FILE = "data/tgju_market_latest.csv"
LATEST_JSON_FILE = "data/tgju_market_latest.json"

MARKETS = [
    {"symbol": "usd", "name": "دلار", "url": "https://www.tgju.org/profile/price_dollar_rl", "market": "free"},
    {"symbol": "gold18", "name": "طلای 18 عیار", "url": "https://www.tgju.org/profile/geram18", "market": "domestic"},
    {"symbol": "sekee", "name": "سکه امامی", "url": "https://www.tgju.org/profile/sekee", "market": "domestic"},
    {"symbol": "sekeb", "name": "سکه بهار آزادی", "url": "https://www.tgju.org/profile/sekeb", "market": "domestic"},
    {"symbol": "nim", "name": "نیم سکه", "url": "https://www.tgju.org/profile/nim", "market": "domestic"},
    {"symbol": "rob", "name": "ربع سکه", "url": "https://www.tgju.org/profile/rob", "market": "domestic"},
    {"symbol": "gerami", "name": "سکه گرمی", "url": "https://www.tgju.org/profile/gerami", "market": "domestic"},
]


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
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return str(value).translate(table)


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


def fetch_page(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_plain_text(html):
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    text = normalize_digits(text)
    text = text.replace("\xa0", " ")
    return " ".join(text.split())


def extract_fields(html):
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
        value = row[1].strip()
        for key, field in wanted.items():
            if label == key or label.startswith(key):
                fields[field] = clean_value(value)

    # TGJU pages do not all expose the same HTML table structure.
    # Use the rendered page text as a robust fallback, especially for coin pages.
    text = extract_plain_text(html)

    # The current TGJU pages may render the label in several forms:
    # "نرخ فعلی:", "نرخ فعلی::", or with HTML whitespace between the label and value.
    # Search for the first number immediately following the label instead of
    # relying on one exact punctuation pattern.
    numeric_patterns = {
        "last_price": r"نرخ\s*فعلی\s*: *\s*([0-9][0-9,٬]*)",
        "yesterday_price": r"نرخ\s*روز\s*گذشته\s*: *\s*([0-9][0-9,٬]*)",
        "price_change_percent": r"درصد\s*تغییر\s*نسبت\s*به\s*روز\s*گذشته\s*: *\s*([0-9]+(?:[.,][0-9]+)?)\s*%?",
        "price_change": r"میزان\s*تغییر\s*نسبت\s*به\s*روز\s*گذشته\s*: *\s*([0-9][0-9,٬]*)",
    }

    for field, pattern in numeric_patterns.items():
        match = re.search(pattern, text, flags=re.I)
        if match:
            fields[field] = clean_value(match.group(1))

    # Extra fallback: some TGJU responses contain more than one colon or
    # additional inline text after the label. In that case, take the first
    # numeric value after "نرخ فعلی".
    if "last_price" not in fields:
        match = re.search(r"نرخ\s*فعلی.*?([0-9][0-9,٬]*)", text, flags=re.I)
        if match:
            fields["last_price"] = clean_value(match.group(1))

    update_match = re.search(r"زمان\s*ثبت\s*آخرین\s*نرخ\s*: *\s*([0-9۰-۹٠-٩:]+)", text)
    if update_match:
        fields["last_update"] = clean_value(update_match.group(1))

    return fields


def build_record(market):
    html = fetch_page(market["url"])
    fields = extract_fields(html)

    if "last_price" not in fields:
        raise RuntimeError(f"TGJU {market['symbol']}: current price was not found at {market['url']}")

    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc.astimezone(ZoneInfo("Asia/Tehran"))

    return {
        "collected_at_utc": now_utc.isoformat(),
        "collected_at_tehran": now_tehran.isoformat(),
        "source": SOURCE,
        "symbol": market["symbol"],
        "asset_name": market["name"],
        "market": market["market"],
        "last_price": to_number(fields.get("last_price")),
        "yesterday_price": to_number(fields.get("yesterday_price")),
        "price_change": to_number(fields.get("price_change")),
        "price_change_percent": to_number(fields.get("price_change_percent")),
        "source_last_update": fields.get("last_update", ""),
        "source_url": market["url"],
    }


def write_latest(records):
    os.makedirs("data", exist_ok=True)
    fields = list(records[0].keys())
    with open(LATEST_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    with open(LATEST_JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)


def append_changed_records(records):
    os.makedirs("data", exist_ok=True)
    existing = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", newline="", encoding="utf-8-sig") as file:
            existing = list(csv.DictReader(file))

    last_by_symbol = {}
    for row in existing:
        last_by_symbol[row.get("symbol", "")] = row

    fields = list(records[0].keys())
    changed_count = 0
    file_exists = os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not file_exists:
            writer.writeheader()

        comparable = ["last_price", "yesterday_price", "price_change", "price_change_percent"]
        for record in records:
            previous = last_by_symbol.get(record["symbol"])
            if previous and all(str(previous.get(key, "")) == str(record.get(key, "")) for key in comparable):
                print(f"{record['symbol']}: unchanged")
                continue
            writer.writerow(record)
            changed_count += 1
            print(f"{record['symbol']}: history updated")

    return changed_count


def main():
    records = []
    for market in MARKETS:
        print(f"Fetching {market['name']} ({market['symbol']}) ...")
        try:
            record = build_record(market)
            records.append(record)
            print(f"  price={record['last_price']} change={record['price_change']} percent={record['price_change_percent']}")
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch {market['symbol']} from TGJU: {exc}") from exc

    write_latest(records)
    changed_count = append_changed_records(records)
    print(json.dumps({"symbols": len(records), "changed_history_rows": changed_count, "latest_file": LATEST_FILE, "history_file": HISTORY_FILE}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
