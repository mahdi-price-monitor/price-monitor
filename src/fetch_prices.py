import os
import json
import csv
from datetime import datetime, timezone
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


def get_price(symbol):
    params = urllib.parse.urlencode({
        "api_key": API_KEY,
        "item": symbol
    })

    url = f"{BASE_URL}?{params}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "price-monitor/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read().decode("utf-8")

    return json.loads(data)


def main():

    collected_at = datetime.now(timezone.utc).isoformat()

    result = {
        "collected_at": collected_at,
        "source": "navasan",
        "prices": {}
    }

    # دریافت قیمت‌ها
    for name, symbol in SYMBOLS.items():

        data = get_price(symbol)

        result["prices"][name] = data

    # ساخت پوشه data
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

    # استخراج اطلاعات برای تاریخچه
    usd = result["prices"]["usd_sell"]["usd_sell"]
    gold = result["prices"]["gold_18k"]["18ayar"]

    history_file = "data/history.csv"

    file_exists = os.path.exists(history_file)

    # اضافه کردن رکورد جدید به تاریخچه
    with open(
        history_file,
        "a",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        fieldnames = [
            "collected_at",
            "usd_date",
            "usd_time",
            "usd_value",
            "usd_change",
            "gold_date",
            "gold_time",
            "gold_18k_value",
            "gold_18k_change"
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        # اگر فایل برای اولین بار ساخته شده، Header ایجاد شود
        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "collected_at": collected_at,

            "usd_date": usd.get("date", ""),
            "usd_time": usd.get("date", "").split(" ")[-1]
            if usd.get("date") else "",

            "usd_value": usd.get("value", ""),
            "usd_change": usd.get("change", ""),

            "gold_date": gold.get("date", ""),
            "gold_time": gold.get("date", "").split(" ")[-1]
            if gold.get("date") else "",

            "gold_18k_value": gold.get("value", ""),
            "gold_18k_change": gold.get("change", "")
        })

    print("Price update completed successfully.")
    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ))


if __name__ == "__main__":
    main()
