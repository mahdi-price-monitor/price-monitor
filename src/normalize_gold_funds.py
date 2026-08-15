import csv

FILE = "data/gold_funds.csv"


def main():
    with open(FILE, "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
        fieldnames = list(rows[0].keys()) if rows else []

    if not rows:
        raise RuntimeError("gold_funds.csv is empty")

    # TGJU supplies a live market price, not an official closing price.
    # Keep closing_price blank rather than incorrectly duplicating last_price.
    for row in rows:
        if row.get("source") == "TGJU":
            row["closing_price"] = ""

    with open(FILE, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Normalized {len(rows)} gold-fund rows.")


if __name__ == "__main__":
    main()
