import csv
import os

LATEST_FILE = "data/tgju_market_latest.csv"
DASHBOARD_FILE = "data/tgju_dashboard.csv"


def main():
    if not os.path.exists(LATEST_FILE):
        raise FileNotFoundError(f"Missing {LATEST_FILE}")

    with open(LATEST_FILE, "r", newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise RuntimeError("TGJU latest data is empty")

    fields = [
        "symbol",
        "asset_name",
        "price",
        "price_change",
        "price_change_percent",
        "last_update",
        "collected_at_tehran",
        "source",
    ]

    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    with open(DASHBOARD_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    print(f"TGJU dashboard output updated: {DASHBOARD_FILE} ({len(rows)} assets)")


if __name__ == "__main__":
    main()
