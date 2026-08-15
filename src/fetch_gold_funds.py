import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

BASE_URL = "https://cdn.tsetmc.com/api"
TGJU_URL = "https://www.tgju.org/profile/gold_17_coin"
OUTPUT_FILE = "data/gold_funds.csv"
GOLD_KEYWORDS = ("طلا", "طلای", "زر", "زرین")

FIELDS = [
    "collected_at_utc", "collected_at_tehran", "source", "symbol", "fund_name",
    "ins_code", "last_price", "closing_price", "yesterday_price", "price_change",
    "price_change_percent", "nav_subscription", "nav_redemption",
]

def get_json(path, attempts=3):
    url = f"{BASE_URL}{path}"
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"})
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"TSETMC request failed (attempt {attempt}/{attempts}): {url} -> {exc}")
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"TSETMC request failed after {attempts} attempts: {url} -> {last_error}")

def get_text(url, attempts=2):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8"})
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            print(f"Web request failed (attempt {attempt}/{attempts}): {url} -> {exc}")
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Web request failed after {attempts} attempts: {url} -> {last_error}")

def first(item, *keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""

def normalize_digits(value):
    text = str(value or "")
    return text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))

def to_number(value):
    if value in (None, ""):
        return ""
    text = normalize_digits(value).replace(",", "").replace("٬", "").replace("%", "").strip()
    try:
        number = float(text)
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
    symbol = str(first(item, "lVal18AFC", "symbol", "symbolName", "lVal18"))
    name = str(first(item, "lVal30", "name", "fundName", "instrumentName"))
    return any(keyword in f"{symbol} {name}" for keyword in GOLD_KEYWORDS)

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
        return (to_number(first(etf, "navSubscription", "nav_subscription", "subscriptionNav", "pNavIssue", "navIssue")),
                to_number(first(etf, "navRedemption", "nav_redemption", "redemptionNav", "pNavCancel", "navCancel")))
    except Exception as exc:
        print(f"NAV unavailable for {ins_code}: {exc}")
        return "", ""

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.current_row=None; self.current_cell=None
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.current_row=[]
        elif tag in ("td", "th") and self.current_row is not None: self.current_cell=[]
    def handle_data(self, data):
        if self.current_cell is not None:
            text=" ".join(data.split())
            if text: self.current_cell.append(text)
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.current_cell is not None:
            self.current_row.append(" ".join(self.current_cell).strip()); self.current_cell=None
        elif tag == "tr" and self.current_row is not None:
            if self.current_row: self.rows.append(self.current_row)
            self.current_row=None

def get_tgju_funds():
    parser=TableParser(); parser.feed(get_text(TGJU_URL)); funds=[]
    for cells in parser.rows:
        if not cells or not cells[0].strip().startswith("صندوق طلای") or len(cells)<2: continue
        name=cells[0].strip(); symbol=name.replace("صندوق طلای", "").strip(); last_price=to_number(cells[1]); change_percent=""; change_value=""
        if len(cells)>=3:
            match=re.search(r"\(?\s*([+-]?\d+(?:[.,]\d+)?)\s*%?\s*\)?", normalize_digits(cells[2]))
            if match: change_percent=to_number(match.group(1))
        if last_price!="" and change_percent!="" and change_percent>-100:
            yesterday=round(last_price/(1+change_percent/100)); change_value=last_price-yesterday
        else: yesterday=""
        funds.append({"symbol":symbol,"fund_name":name,"ins_code":"","last_price":last_price,"closing_price":"","yesterday_price":yesterday,"price_change":change_value,"price_change_percent":change_percent,"nav_subscription":"","nav_redemption":""})
    if not funds: raise RuntimeError("TGJU gold-fund table was found, but no gold-fund rows could be parsed.")
    return funds

def write_rows(rows, now_utc, now_tehran):
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE,"w",newline="",encoding="utf-8-sig") as file:
        writer=csv.DictWriter(file,fieldnames=FIELDS); writer.writeheader()
        for row in rows: writer.writerow({"collected_at_utc":now_utc.isoformat(),"collected_at_tehran":now_tehran.isoformat(),**row})
    print(f"Saved {len(rows)} gold funds to {OUTPUT_FILE}")
    for row in rows: print(row["symbol"],row["last_price"],row["closing_price"])

def main():
    now_utc=datetime.now(timezone.utc); now_tehran=now_utc.astimezone(ZoneInfo("Asia/Tehran"))
    try:
        funds=get_commodity_funds()
        if not funds: raise RuntimeError("No gold funds were found in TSETMC CommodityFund data.")
        rows=[]
        for fund in funds:
            ins_code=str(first(fund,"insCode","inscode")); symbol=first(fund,"lVal18AFC","symbol","symbolName","lVal18"); fund_name=first(fund,"lVal30","name","fundName","instrumentName")
            last_price=to_number(first(fund,"pDrCotVal","lastPrice","lastprice")); closing_price=to_number(first(fund,"pClosing","closingPrice","closingprice")); yesterday_price=to_number(first(fund,"priceYesterday","yesterdayPrice","yesterdayprice"))
            if last_price=="" and ins_code:
                try:
                    info=get_json(f"/ClosingPrice/GetClosingPriceInfo/{ins_code}").get("closingPriceInfo",{}); last_price=to_number(first(info,"pDrCotVal","lastPrice")); closing_price=to_number(first(info,"pClosing","closingPrice")); yesterday_price=to_number(first(info,"priceYesterday","yesterdayPrice"))
                except Exception as exc: print(f"Price unavailable for {symbol}: {exc}")
            change=last_price-yesterday_price if last_price!="" and yesterday_price!="" else ""; nav_subscription,nav_redemption=get_etf_nav(ins_code)
            rows.append({"source":"TSETMC","symbol":symbol,"fund_name":fund_name,"ins_code":ins_code,"last_price":last_price,"closing_price":closing_price,"yesterday_price":yesterday_price,"price_change":change,"price_change_percent":percent(change,yesterday_price),"nav_subscription":nav_subscription,"nav_redemption":nav_redemption})
        write_rows(rows,now_utc,now_tehran)
    except Exception as exc:
        print(f"TSETMC collector unavailable: {exc}"); print("Falling back to TGJU gold-fund market table...")
        rows=get_tgju_funds()
        for row in rows: row["source"]="TGJU"
        write_rows(rows,now_utc,now_tehran)

if __name__ == "__main__": main()
