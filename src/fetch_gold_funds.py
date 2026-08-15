import csv
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BASE_URL = "https://cdn.tsetmc.com/api"
OUTPUT_FILE = "data/gold_funds.csv"

# CommodityFund gives a market-oriented list of commodity funds.
# We then keep instruments whose Persian symbol/name identifies them as gold funds.
GOLD_KEYWORDS = ("طلا", "طلای", "سکه طلا", "زر", "زرین")

FIELDS = [
    "collected_at_utc",
    "collected_at_tehran",
    "symbol",
    "fund_name",
    "ins_code",
    "last_price",
    "closing_price",
    "yesterday_price",
    "price_change",
    "price_change_percent",
    "nav_subscription",
    "nav_redemption",
]


def get_json(path):
    url = f"{BASE_URL}{path}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (price-monitor)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def first(item, *keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""


def to_number(value):
    if value in (None, ""):
        return ""
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (ValueError, TypeError):
        return ""


def percent(change, yesterday):
    change = to_number(change)
    yesterday = to_number(yesterday)
    if change == "" or yesterday in ("", 0):
        return ""
    return round(change / yesterday * 100, 4)


def is_gold_fund(item):
    text = " ".join(
        str(first(item, "lVal18AFC", "symbol", "symbolName", "lVal18", "")),
        str(first(item, "lVal30", "name", "fundName", "instrumentName", "")),
    )
    return any(keyword in text for keyword in GOLD_KEYWORDS)


def get_commodity_funds():
    data = get_json("/ClosingPrice/GetTradeTop/CommodityFund/0/100")
    rows = data.get("tradeTop", [])
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected TSETMC CommodityFund response format.")
    return [row for row in rows if is_gold_fund(row)]


def get_etf_nav(ins_code):
    if not ins_code:
        return "", ""
    try:
        data = get_json(f"/Fund/GetETFByInsCode/{ins_code}")
        etf = data.get("etf", {})
        if not isinstance(etf, dict):
            return "", ""

        subscription = first(
            etf,
            "navSubscription",
            "nav_subscription",
            "subscriptionNav",
            "pNavIssue",
            "navIssue",
        )
        redemption = first(
            etf,
            "navRedemption",
            "nav_redemption",
            "redemptionNav",
            "pNavCancel",
            "navCancel",
        )
        return to_number(subscription), to_number(redemption)
    except Exception as exc:
        print(f"NAV unavailable for {ins_code}: {exc}")
        return "", ""


def main():
    now_utc = datetime.now(timezone.utc)
    now_tehran = now_utc.astimezone(ZoneInfo("Asia/Tehran"))

    funds = get_commodity_funds()
    if not funds:
        raise RuntimeError("No gold funds were found in TSETMC CommodityFund data.")

    rows = []
    for fund in funds:
        ins_code = str(first(fund, "insCode", "inscode"))
        symbol = first(fund, "lVal18AFC", "symbol", "symbolName", "lVal18")
        fund_name = first(fund, "lVal30", "name", "fundName", "instrumentName")

        last_price = to_number(first(fund, "pDrCotVal", "lastPrice", "lastprice"))
        closing_price = to_number(first(fund, "pClosing", "closingPrice", "closingprice"))
        yesterday_price = to_number(first(fund, "priceYesterday", "yesterdayPrice", "yesterdayprice"))

        if last_price == "" and ins_code:
            try:
                info = get_json(f"/ClosingPrice/GetClosingPriceInfo/{ins_code}").get("closingPriceInfo", {})
                last_price = to_number(first(info, "pDrCotVal", "lastPrice"))
                closing_price = to_number(first(info, "pClosing", "closingPrice"))
                yesterday_price = to_number(first(info, "priceYesterday", "yesterdayPrice"))
            except Exception as exc:
                print(f"Price unavailable for {symbol}: {exc}")

        change = ""
        if last_price != "" and yesterday_price != "":
            change = last_price - yesterday_price

        nav_subscription, nav_redemption = get_etf_nav(ins_code)

        rows.append({
            "collected_at_utc": now_utc.isoformat(),
            "collected_at_tehran": now_tehran.isoformat(),
            "symbol": symbol,
            "fund_name": fund_name,
            "ins_code": ins_code,
            "last_price": last_price,
            "closing_price": closing_price,
            "yesterday_price": yesterday_price,
            "price_change": change,
            "price_change_percent": percent(change, yesterday_price),
            "nav_subscription": nav_subscription,
            "nav_redemption": nav_redemption,
        })

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} gold funds to {OUTPUT_FILE}")
    for row in rows:
        print(row["symbol"], row["last_price"], row["closing_price"])


if __name__ == "__main__":
    main()
