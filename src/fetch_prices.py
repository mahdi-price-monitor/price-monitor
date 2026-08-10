import os
import json
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import urllib.request
import urllib.parse


API_KEY = os.environ.get("NAVASAN_API_KEY")

if not API_KEY:
    raise RuntimeError("NAVASAN_API_KEY is not configured.")


BASE_URL = "http://api.navasan.tech/latest/"

SYMBOLS = {
    "usd_sell": "usd_sell",
    "gold_18k": "18ayar",
}

HISTORY_FILE = "data/history.csv"

HISTORY_FIELDS = [
    "collected_at_utc",
    "collected_at_tehran",
    "usd_date",
    "usd_time",
    "usd_value",
    "usd_change",
    "usd_change_percent",
    "gold_date",
    "gold_time",
    "gold_18k_value",
    "gold_18k_change",
    "gold_18k_change_percent",
]


def get_price(symbol):
    params = urllib.parse.urlencode({
        "api_key": API_KEY,
        "item": symbol
    })

    url = f"{BASE_URL}?{params}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "price-monitor/2.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read().decode("utf-8")

    return json.loads(data)


def to_number(value):
    if value is None or value == "":
        return None

    try:
        number = float(value)

        if number.is_integer():
            return int(number)

        return number

    except (ValueError, TypeError):
        return None


def calculate_percent(value, change):
    value = to_number(value)
    change = to_number(change)

    if value is None or change is None:
        return ""

    previous_value = value - change

    if previous_value == 0:
        return ""

    return round((change / previous_value) * 100, 4)


def convert_to_tehran(utc_datetime):
    tehran = ZoneInfo("Asia/Tehran")
    return utc_datetime.astimezone(tehran)


def migrate_old_history():
    """
    اگر history.csv قدیمی باشد، آن را به ساختار جدید تبدیل می‌کند
    و اطلاعات قبلی را حفظ می‌کند.
    """

    if not os.path.exists(HISTORY_FILE):
        return

    with open(
        HISTORY_FILE,
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)
        old_rows = list(reader)
        old_fields = reader.fieldnames or []

    if old_fields == HISTORY_FIELDS:
        return

    new_rows = []

    for row in old_rows:

        usd_value = row.get("usd_value", "")
        usd_change = row.get("usd_change", "")

        gold_value = row.get("gold_18k_value", "")
        gold_change = row.get("gold_18k_change", "")

        collected_at_utc = row.get(
            "collected_at_utc",
            row.get("collected_at", "")
        )

        collected_at_tehran = ""

        try:
            if collected_at_utc:
                dt = datetime.fromisoformat(
                    collected_at_utc.replace("Z", "+00:00")
                )

                if dt.tzinfo is not None:
                    collected_at_tehran = (
                        convert_to_tehran(dt).isoformat()
                    )

        except Exception:
            collected_at_tehran = ""

        new_rows.append({
            "collected_at_utc": collected_at_utc,
            "collected_at_tehran": collected_at_tehran,

            "usd_date": row.get("usd_date", ""),
            "usd_time": row.get("usd_time", ""),
            "usd_value": usd_value,
            "usd_change": usd_change,

            "usd_change_percent": calculate_percent(
                usd_value,
                usd_change
            ),

            "gold_date": row.get("gold_date", ""),
            "gold_time": row.get("gold_time", ""),
            "gold_18k_value": gold_value,
            "gold_18k_change": gold_change,

            "gold_18k_change_percent": calculate_percent(
                gold_value,
                gold_change
            ),
        })

    with open(
        HISTORY_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=HISTORY_FIELDS
        )

        writer.writeheader()
        writer.writerows(new_rows)


def main():

    # زمان دریافت
    collected_at_utc_dt = datetime.now(timezone.utc)

    collected_at_utc = collected_at_utc_dt.isoformat()

    collected_at_tehran = (
        convert_to_tehran(
            collected_at_utc_dt
        ).isoformat()
    )

    result = {
        "collected_at": collected_at_utc,
        "source": "navasan",
        "prices": {}
    }

    # دریافت قیمت‌ها
    for name, symbol in SYMBOLS.items():

        data = get_price(symbol)

        result["prices"][name] = data

    # ایجاد پوشه data
    os.makedirs("data", exist_ok=True)

    # ذخیره آخرین اطلاعات
    with open(
        "data/latest.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    # تبدیل history قدیمی به ساختار جدید
    migrate_old_history()

    # استخراج اطلاعات دلار
    usd = result["prices"]["usd_sell"]["usd_sell"]

    usd_value = to_number(
        usd.get("value")
    )

    usd_change = to_number(
        usd.get("change")
    )

    # استخراج اطلاعات طلا
    gold = result["prices"]["gold_18k"]["18ayar"]

    gold_value = to_number(
        gold.get("value")
    )

    gold_change = to_number(
        gold.get("change")
    )

    # ایجاد رکورد جدید
    new_record = {
        "collected_at_utc": collected_at_utc,

        "collected_at_tehran": collected_at_tehran,

        "usd_date": usd.get("date", ""),

        "usd_time": (
            usd.get("date", "").split(" ")[-1]
            if usd.get("date")
            else ""
        ),

        "usd_value": usd_value,

        "usd_change": usd_change,

        "usd_change_percent": calculate_percent(
            usd_value,
            usd_change
        ),

        "gold_date": gold.get("date", ""),

        "gold_time": (
            gold.get("date", "").split(" ")[-1]
            if gold.get("date")
            else ""
        ),

        "gold_18k_value": gold_value,

        "gold_18k_change": gold_change,

        "gold_18k_change_percent": calculate_percent(
            gold_value,
            gold_change
        ),
    }

    # اضافه کردن رکورد جدید
    with open(
        HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=HISTORY_FIELDS
        )

        # اگر فایل خالی بود Header ایجاد شود
        if file.tell() == 0:
            writer.writeheader()

        writer.writerow(new_record)

    print("Price update completed successfully.")

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()
