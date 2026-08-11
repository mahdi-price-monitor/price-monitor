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

# Navasan returns all latest prices when item is omitted.
# This keeps the free-plan usage to one API request per workflow run.
ASSETS = {
    "usd_sell": {
        "symbol": "usd_sell",
        "prefix": "usd",
    },
    "gold_18k": {
        "symbol": "18ayar",
        "prefix": "gold_18k",
    },
    "xau": {
        "symbol": "xau",
        "prefix": "xau",
    },
    "sekkeh": {
        "symbol": "sekkeh",
        "prefix": "sekkeh",
    },
    "bahar": {
        "symbol": "bahar",
        "prefix": "bahar",
    },
    "nim": {
        "symbol": "nim",
        "prefix": "nim",
    },
    "rob": {
        "symbol": "rob",
        "prefix": "rob",
    },
    "gerami": {
        "symbol": "gerami",
        "prefix": "gerami",
    },
    "abshodeh": {
        "symbol": "abshodeh",
        "prefix": "abshodeh",
    },
}

HISTORY_FILE = "data/history.csv"

HISTORY_FIELDS = [
    "collected_at_utc",
    "collected_at_tehran",
]

for asset in ASSETS.values():
    prefix = asset["prefix"]
    HISTORY_FIELDS.extend([
        f"{prefix}_date",
        f"{prefix}_time",
        f"{prefix}_value",
        f"{prefix}_change",
        f"{prefix}_change_percent",
    ])


def get_latest_prices():
    """
    دریافت تمام نرخ‌های آخرین وضعیت نوسان در یک درخواست.

    چون پارامتر item ارسال نمی‌شود، API آخرین نرخ همه نمادها
    را برمی‌گرداند و مصرف سهمیه فقط یک درخواست در هر اجراست.
    """

    params = urllib.parse.urlencode({
        "api_key": API_KEY
    })

    url = f"{BASE_URL}?{params}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "price-monitor/4.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read().decode("utf-8")

    latest = json.loads(data)

    if not isinstance(latest, dict):
        raise RuntimeError("Unexpected Navasan API response format.")

    missing = [
        asset["symbol"]
        for asset in ASSETS.values()
        if asset["symbol"] not in latest
    ]

    if missing:
        raise RuntimeError(
            "Navasan API did not return required symbols: "
            + ", ".join(missing)
        )

    return latest


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


def create_asset_record(asset_data, prefix):
    value = to_number(asset_data.get("value"))
    change = to_number(asset_data.get("change"))
    date = asset_data.get("date", "")

    return {
        f"{prefix}_date": date,
        f"{prefix}_time": date.split(" ")[-1] if date else "",
        f"{prefix}_value": value,
        f"{prefix}_change": change,
        f"{prefix}_change_percent": calculate_percent(value, change),
    }


def create_record(
    collected_at_utc,
    collected_at_tehran,
    prices
):
    record = {
        "collected_at_utc": collected_at_utc,
        "collected_at_tehran": collected_at_tehran,
    }

    for asset in ASSETS.values():
        symbol = asset["symbol"]
        prefix = asset["prefix"]
        record.update(
            create_asset_record(prices[symbol], prefix)
        )

    return record


def get_market_key(row):
    """
    کلید وضعیت بازار.

    زمان‌های نوسان در تشخیص تکراری بودن دخالت ندارند؛
    فقط مقدار و تغییر همه دارایی‌های پایش‌شده مقایسه می‌شوند.
    """

    key = []

    for asset in ASSETS.values():
        prefix = asset["prefix"]
        key.extend([
            str(row.get(f"{prefix}_value", "")),
            str(row.get(f"{prefix}_change", "")),
        ])

    return tuple(key)


def clean_history():
    """
    تاریخچه موجود را می‌خواند، رکوردهای تکراری را حذف می‌کند
    و با ساختار فعلی ذخیره می‌کند.

    رکوردهای قدیمی که ستون‌های دارایی‌های جدید را ندارند
    حفظ می‌شوند و برای ستون‌های جدید مقدار خالی می‌گیرند.
    """

    if not os.path.exists(HISTORY_FILE):
        return []

    with open(
        HISTORY_FILE,
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    cleaned_rows = []
    seen = set()

    for row in rows:
        normalized = {
            field: row.get(field, "") or ""
            for field in HISTORY_FIELDS
        }

        key = get_market_key(normalized)

        if key in seen:
            continue

        seen.add(key)

        collected_at_utc = normalized.get(
            "collected_at_utc",
            ""
        )

        collected_at_tehran = normalized.get(
            "collected_at_tehran",
            ""
        )

        if not collected_at_tehran and collected_at_utc:
            try:
                dt = datetime.fromisoformat(
                    collected_at_utc.replace("Z", "+00:00")
                )

                if dt.tzinfo is not None:
                    collected_at_tehran = (
                        convert_to_tehran(dt).isoformat()
                    )

            except Exception:
                pass

        normalized["collected_at_utc"] = collected_at_utc
        normalized["collected_at_tehran"] = collected_at_tehran

        # Recalculate percentages for legacy rows when possible.
        for asset in ASSETS.values():
            prefix = asset["prefix"]
            percent_field = f"{prefix}_change_percent"

            if not normalized.get(percent_field):
                normalized[percent_field] = calculate_percent(
                    normalized.get(f"{prefix}_value", ""),
                    normalized.get(f"{prefix}_change", "")
                )

        cleaned_rows.append(normalized)

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
        writer.writerows(cleaned_rows)

    return cleaned_rows


def append_if_changed(new_record, existing_rows):
    """
    فقط زمانی رکورد جدید اضافه می‌شود که وضعیت بازار
    نسبت به آخرین رکورد تغییر کرده باشد.
    """

    if existing_rows:
        last_record = existing_rows[-1]

        old_key = get_market_key(last_record)
        new_key = get_market_key(new_record)

        if old_key == new_key:
            print(
                "Market data has not changed. "
                "No new history record added."
            )
            return False

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
        writer.writerow(new_record)

    print("New market record added to history.")
    return True


def main():
    collected_at_utc_dt = datetime.now(timezone.utc)
    collected_at_utc = collected_at_utc_dt.isoformat()
    collected_at_tehran = convert_to_tehran(
        collected_at_utc_dt
    ).isoformat()

    latest_prices = get_latest_prices()

    result = {
        "collected_at": collected_at_utc,
        "source": "navasan",
        "prices": {}
    }

    for name, asset in ASSETS.items():
        symbol = asset["symbol"]
        result["prices"][name] = latest_prices[symbol]

    os.makedirs("data", exist_ok=True)

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

    existing_rows = clean_history()

    new_record = create_record(
        collected_at_utc,
        collected_at_tehran,
        latest_prices
    )

    append_if_changed(
        new_record,
        existing_rows
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )


if __name__ == "__main__":
    main()
