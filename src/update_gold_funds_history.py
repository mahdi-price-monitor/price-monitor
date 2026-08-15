import csv
import os

INPUT_FILE = "data/gold_funds.csv"
HISTORY_FILE = "data/gold_funds_history.csv"

def main():
    if not os.path.exists(INPUT_FILE): raise FileNotFoundError(INPUT_FILE)
    with open(INPUT_FILE, "r", encoding="utf-8-sig", newline="") as file:
        rows=list(csv.DictReader(file))
    if not rows: raise RuntimeError("gold_funds.csv is empty")
    fieldnames=list(rows[0].keys()); timestamp=rows[0].get("collected_at_utc","")
    if not timestamp: raise RuntimeError("gold_funds.csv has no collection timestamp")
    existing=set()
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE,"r",encoding="utf-8-sig",newline="") as file:
            for row in csv.DictReader(file): existing.add((row.get("collected_at_utc",""),row.get("symbol","")))
    new_rows=[row for row in rows if (row.get("collected_at_utc",""),row.get("symbol","")) not in existing]
    if not new_rows:
        print("No new gold-fund history rows to append."); return
    os.makedirs(os.path.dirname(HISTORY_FILE),exist_ok=True); write_header=not os.path.exists(HISTORY_FILE) or os.path.getsize(HISTORY_FILE)==0
    with open(HISTORY_FILE,"a",encoding="utf-8-sig",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=fieldnames)
        if write_header: writer.writeheader()
        writer.writerows(new_rows)
    print(f"Appended {len(new_rows)} gold-fund history rows for {timestamp}.")

if __name__ == "__main__": main()
