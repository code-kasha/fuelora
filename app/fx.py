"""Exchange rates for the currency selector, from the ECB daily reference rates.

ECB rates are units of each currency per 1 EUR. Conversion goes through EUR.
"""

import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
USER_AGENT = "fuelora/0.1 (personal research; one request per refresh)"


def fetch_rates(out_path: Path, retrieved_at: str) -> int:
    """Fetch ECB daily rates and write them as JSON. Returns the number of currencies."""
    request = urllib.request.Request(ECB_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    rates = {"EUR": 1.0}
    for element in root.iter():
        code, rate = element.get("currency"), element.get("rate")
        if code and rate:
            rates[code] = float(rate)
    if len(rates) < 5:
        raise ValueError("ECB response did not contain the expected rates")

    tmp_path = out_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps({"retrieved_at": retrieved_at, "rates": rates}), encoding="utf-8")
    tmp_path.replace(out_path)
    return len(rates)


def read_rates(path: Path) -> dict[str, float]:
    return json.loads(path.read_text(encoding="utf-8"))["rates"]


def convert(amount: float, rates: dict[str, float], source: str, target: str) -> float:
    return amount / rates[source] * rates[target]
