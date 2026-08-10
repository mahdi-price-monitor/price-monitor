import os
import json
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

    for name, symbol in SYMBOLS.items():
        try:
            data = get_price(symbol)

            result["prices"][name] = data

        except Exception as error:
            result["prices"][name] = {
                "error": str(error)
            }

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

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2
    ))


if __name__ == "__main__":
    main()
