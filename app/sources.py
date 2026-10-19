"""Data sources for Fuelora: fetch, parse, validate and cache fuel prices.

Each source fetch is one HTTP request. Results are validated before they replace
the cache, so a failed or partial fetch never overwrites good data.

Local (India) prices come from Goodreturns, which lists states and UTs.
Global prices come from GlobalPetrolPrices, which lists one national price per country.
"""

import csv
import datetime as dt
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

USER_AGENT = "fuelora/0.1 (personal research; one request per refresh)"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)")

GOODRETURNS = {
    "petrol": "https://www.goodreturns.in/petrol-price.html",
    "diesel": "https://www.goodreturns.in/diesel-price.html",
}
GLOBALPETROL = {
    "petrol": "https://www.globalpetrolprices.com/gasoline_prices/",
    "diesel": "https://www.globalpetrolprices.com/diesel_prices/",
    "kerosene": "https://www.globalpetrolprices.com/kerosene_prices/",
}


@dataclass(frozen=True)
class Dataset:
    """One fuel and scope. `fetch` is None when no usable source exists yet."""
    fuel: str
    scope: str  # "local" or "global"
    unit: str  # "INR" or "USD" per litre
    refresh_seconds: int
    source_name: str
    fetch: Callable[[Path], int] | None = None
    note: str = ""
    unit_word: str = "litre"  # how the price is quoted: "litre" or "barrel"

    @property
    def key(self) -> str:
        return f"{self.fuel}_{self.scope}"

    @property
    def path(self) -> Path:
        return DATA_DIR / f"{self.key}.csv"


# ---- HTTP and cache helpers -------------------------------------------------

def fetch_page(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def write_rows(out_path: Path, rows: list[tuple[str, float]], source: str) -> int:
    """Write validated rows atomically. Returns the number of rows written."""
    retrieved_at = dt.datetime.now(IST).isoformat(timespec="minutes")
    tmp_path = out_path.with_suffix(".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "price", "retrieved_at", "source"])
        for name, price in rows:
            writer.writerow([name, f"{price:.3f}", retrieved_at, source])
    os.replace(tmp_path, out_path)
    return len(rows)


def read_rows(path: Path) -> tuple[list[tuple[str, float]], str]:
    """Return (rows, retrieved_at) from a cache file."""
    with path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    rows = [(r["name"], float(r["price"])) for r in records]
    return rows, records[0]["retrieved_at"]


def _dedupe(rows: list[tuple[str, float]]) -> list[tuple[str, float]]:
    seen, unique = set(), []
    for name, price in rows:
        if name not in seen:
            seen.add(name)
            unique.append((name, price))
    return unique


def _check_range(rows: list[tuple[str, float]], low: float, high: float) -> None:
    bad = [(name, price) for name, price in rows if not low <= price <= high]
    if bad:
        raise ValueError(f"prices outside expected range: {bad[:3]}")


# ---- Goodreturns (India, states and UTs) -----------------------------------

class _TableParser(HTMLParser):
    """Collects cell text from every table with class 'gr-table', grouped by row."""

    def __init__(self, class_filter: str | None = None):
        super().__init__()
        self.class_filter = class_filter
        self.tables: list[list[list[str]]] = []
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class") or ""
        if tag == "table" and (self.class_filter is None or self.class_filter in classes):
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_goodreturns(page: str, min_rows: int = 34) -> list[tuple[str, float]]:
    """Return (state_or_ut, price) pairs from the first large price table."""
    parser = _TableParser()
    parser.feed(page)
    for table in parser.tables:
        rows = []
        for cells in table:
            if len(cells) < 2:
                continue
            match = PRICE_RE.search(cells[1])
            if cells[0] and match:
                rows.append((cells[0], float(match.group(1))))
        rows = _dedupe(rows)
        if len(rows) >= min_rows:
            return rows
    raise ValueError("price table not found or too few rows")


# ---- Cardekho (India, second source for cross-checks and Andhra Pradesh) ----

CARDEKHO = {
    "petrol": "https://www.cardekho.com/petrol-price",
    "diesel": "https://www.cardekho.com/diesel-price",
}
# Names that differ between the two sites, mapped to the Goodreturns spelling.
NAME_ALIASES = {
    "Pondicherry": "Pondicherry",
    "Puducherry": "Pondicherry",
    "Chhatisgarh": "Chhattisgarh",
    "Chhattisgarh": "Chhattisgarh",
}
CROSSCHECK_THRESHOLD = 1.0  # INR per litre


def parse_cardekho(page: str) -> list[tuple[str, float]]:
    """Return (state, price) pairs from the table whose header row starts with 'State'."""
    parser = _TableParser()
    parser.feed(page)
    for table in parser.tables:
        table = [row for row in table if row]  # Cardekho puts an empty row before the header
        if not table or table[0][:1] != ["State"]:
            continue
        rows = []
        for cells in table[1:]:
            if len(cells) != 2:
                continue
            match = PRICE_RE.search(cells[1])
            if cells[0] and match:
                name = NAME_ALIASES.get(cells[0], cells[0])
                rows.append((name, float(match.group(1))))
        rows = _dedupe(rows)
        if len(rows) >= 30:
            return rows
    raise ValueError("Cardekho state table not found")


def make_local_fetch(fuel: str) -> Callable[[Path], int]:
    """Goodreturns is the primary table. Cardekho gives a cross-check and fills Andhra Pradesh."""
    url = GOODRETURNS[fuel]
    check_path = DATA_DIR / f"{fuel}_local_check.csv"

    def fetch(out_path: Path) -> int:
        rows = parse_goodreturns(fetch_page(url))
        _check_range(rows, 50.0, 200.0)  # INR per litre sanity bounds

        try:
            check = parse_cardekho(fetch_page(CARDEKHO[fuel]))
            _check_range(check, 50.0, 200.0)
            write_rows(check_path, check, CARDEKHO[fuel])
        except Exception:  # noqa: BLE001 - the cross-check is optional; never block the main table
            if check_path.exists():
                check_path.unlink()  # never compare against an old cross-check
            check = []

        present = {name for name, _ in rows}
        for name, price in check:
            if name not in present and name == "Andhra Pradesh":
                rows.append((name, price))
        return write_rows(out_path, rows, f"{url} (cross-check: {CARDEKHO[fuel]})")

    return fetch


# ---- GlobalPetrolPrices (world, one price per country) ---------------------

NAME_RE = re.compile(r"graph_outside_link'>([^<]*?)(?:&nbsp;|\s)*</a>")
GLOBAL_PRICE_RE = re.compile(r'color: #000000;">([\d.]+)</div>')


def parse_globalpetrol(page: str) -> list[tuple[str, float]]:
    """Pair country names with prices. The page lists both in the same ascending order.

    Names and prices are pulled separately, so the counts must match and the prices
    must be ascending. Anything else means the page layout changed, and we refuse.
    """
    names = [n.replace("*", "").strip() for n in NAME_RE.findall(page)]
    prices = [float(p) for p in GLOBAL_PRICE_RE.findall(page)]
    if not names or len(names) != len(prices):
        raise ValueError(f"country names ({len(names)}) and prices ({len(prices)}) do not line up")
    if any(a > b for a, b in zip(prices, prices[1:])):
        raise ValueError("prices are not in ascending order; page layout may have changed")
    return _dedupe(list(zip(names, prices)))


def make_globalpetrol_fetch(fuel: str) -> Callable[[Path], int]:
    url = GLOBALPETROL[fuel]

    def fetch(out_path: Path) -> int:
        rows = parse_globalpetrol(fetch_page(url))
        if len(rows) < 50:
            raise ValueError(f"only {len(rows)} countries found; expected about 60 or more")
        _check_range(rows, 0.0, 10.0)  # USD per litre sanity bounds
        return write_rows(out_path, rows, url)

    return fetch


# ---- EIA (crude oil benchmarks, US dollars per barrel) ----------------------

ROOT = Path(__file__).resolve().parent.parent
EIA_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
CRUDE_SERIES = {
    "EPCBRENT": "Brent crude (Europe spot)",
    "EPCWTI": "WTI crude (Cushing spot)",
}


def eia_key() -> str | None:
    """The EIA API key from the environment, or from the .env file in the project root."""
    value = os.environ.get("EIA_API_KEY")
    if value:
        return value.strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("EIA_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return None


def make_eia_fetch() -> Callable[[Path], int]:
    def fetch(out_path: Path) -> int:
        key = eia_key()
        if not key:
            raise ValueError("EIA_API_KEY is not set")
        query = urlencode([
            ("api_key", key), ("frequency", "daily"), ("data[0]", "value"),
            ("facets[product][]", "EPCBRENT"), ("facets[product][]", "EPCWTI"),
            ("sort[0][column]", "period"), ("sort[0][direction]", "desc"), ("length", "20"),
        ])
        try:
            page = fetch_page(f"{EIA_URL}?{query}")
        except Exception as exc:  # noqa: BLE001 - keep the key out of error messages and the page
            raise ValueError(f"EIA request failed ({type(exc).__name__})") from None
        rows = latest_crude_rows(json.loads(page)["response"]["data"])
        _check_range(rows, 1.0, 500.0)  # USD per barrel sanity bounds
        return write_rows(out_path, rows, "EIA (api.eia.gov)")

    return fetch


def latest_crude_rows(records: list[dict]) -> list[tuple[str, float]]:
    """Latest non-empty value per benchmark. Records must be sorted newest first."""
    latest: dict[str, dict] = {}
    for record in records:
        product = record.get("product")
        if product in CRUDE_SERIES and product not in latest and record.get("value") not in (None, ""):
            latest[product] = record
    missing = sorted(set(CRUDE_SERIES) - set(latest))
    if missing:
        raise ValueError(f"no recent values returned for {missing}")
    return [(f"{CRUDE_SERIES[p]} · {latest[p]['period']}", float(latest[p]["value"])) for p in CRUDE_SERIES]


# ---- Presentation helpers stored with the data -----------------------------

# Country name as printed on GlobalPetrolPrices -> ISO 3166-1 alpha-2 code, for flag images.
COUNTRY_CODES = {
    "Afghanistan": "af", "Albania": "al", "Algeria": "dz", "Andorra": "ad", "Angola": "ao",
    "Argentina": "ar", "Armenia": "am", "Aruba": "aw", "Australia": "au", "Austria": "at",
    "Azerbaijan": "az", "Bahamas": "bs", "Bahrain": "bh", "Bangladesh": "bd", "Barbados": "bb",
    "Belarus": "by", "Belgium": "be", "Belize": "bz", "Benin": "bj", "Bhutan": "bt", "Bolivia": "bo",
    "Bosnia and Herzegovina": "ba", "Bosnia & Herz.": "ba", "Botswana": "bw", "Brazil": "br",
    "Bulgaria": "bg", "Burkina Faso": "bf", "Burma": "mm", "Burma (Myanmar)": "mm", "Myanmar": "mm",
    "Burundi": "bi", "Cambodia": "kh", "Cameroon": "cm", "Canada": "ca", "Cape Verde": "cv",
    "Cayman Islands": "ky", "Central African Republic": "cf", "C. Afr. Rep.": "cf", "Chile": "cl",
    "China": "cn", "Colombia": "co", "Costa Rica": "cr", "Croatia": "hr", "Cuba": "cu",
    "Curacao": "cw", "Curaçao": "cw", "Cyprus": "cy", "Czech Republic": "cz", "Denmark": "dk",
    "Dominica": "dm", "Dominican Republic": "do", "Dom. Rep.": "do", "DR Congo": "cd",
    "Ecuador": "ec", "Egypt": "eg", "El Salvador": "sv", "Estonia": "ee", "Eswatini": "sz",
    "Swaziland": "sz", "Ethiopia": "et", "Fiji": "fj", "Finland": "fi", "France": "fr", "Gabon": "ga",
    "Georgia": "ge", "Germany": "de", "Ghana": "gh", "Greece": "gr", "Grenada": "gd", "Guatemala": "gt",
    "Guinea": "gn", "Guyana": "gy", "Haiti": "ht", "Honduras": "hn", "Hong Kong": "hk", "Hungary": "hu",
    "Iceland": "is", "India": "in", "Indonesia": "id", "Iran": "ir", "Iraq": "iq", "Ireland": "ie",
    "Israel": "il", "Italy": "it", "Ivory Coast": "ci", "Jamaica": "jm", "Japan": "jp", "Jordan": "jo",
    "Kazakhstan": "kz", "Kenya": "ke", "Kuwait": "kw", "Kyrgyzstan": "kg", "Laos": "la", "Latvia": "lv",
    "Lebanon": "lb", "Lesotho": "ls", "Liberia": "lr", "Libya": "ly", "Liechtenstein": "li",
    "Lithuania": "lt", "Luxembourg": "lu", "Madagascar": "mg", "Malawi": "mw", "Malaysia": "my",
    "Maldives": "mv", "Mali": "ml", "Malta": "mt", "Mauritius": "mu", "Mayotte": "yt", "Mexico": "mx",
    "Moldova": "md", "Monaco": "mc", "Mongolia": "mn", "Montenegro": "me", "Morocco": "ma",
    "Mozambique": "mz", "Namibia": "na", "Nepal": "np", "Netherlands": "nl", "New Zealand": "nz",
    "Nicaragua": "ni", "Niger": "ne", "Nigeria": "ng", "North Macedonia": "mk", "N. Maced.": "mk",
    "Norway": "no", "Oman": "om", "Pakistan": "pk", "Panama": "pa", "Paraguay": "py", "Peru": "pe",
    "Philippines": "ph", "Poland": "pl", "Portugal": "pt", "Puerto Rico": "pr", "Qatar": "qa",
    "Romania": "ro", "Russia": "ru", "Rwanda": "rw", "Saint Lucia": "lc", "San Marino": "sm",
    "Saudi Arabia": "sa", "Senegal": "sn", "Serbia": "rs", "Seychelles": "sc", "Sierra Leone": "sl",
    "Singapore": "sg", "Slovakia": "sk", "Slovenia": "si", "South Africa": "za", "South Korea": "kr",
    "Spain": "es", "Sri Lanka": "lk", "Sudan": "sd", "Suriname": "sr", "Sweden": "se", "Switzerland": "ch",
    "Syria": "sy", "Taiwan": "tw", "Tanzania": "tz", "Thailand": "th", "Togo": "tg",
    "Trinidad & Tobago": "tt", "Trinidad and Tobago": "tt", "Tunisia": "tn", "Turkey": "tr",
    "Turkmenistan": "tm", "UAE": "ae", "UK": "gb", "United Kingdom": "gb", "Uganda": "ug",
    "Ukraine": "ua", "Uruguay": "uy", "USA": "us", "United States": "us", "Uzbekistan": "uz",
    "Venezuela": "ve", "Vietnam": "vn", "Wallis and Futuna": "wf", "Zambia": "zm", "Zimbabwe": "zw",
}

# Indian states and UTs (as named by Goodreturns, plus common alternative spellings)
# -> (two-letter code, zone). The zone sets the colour of the dot shown next to each name.
STATE_INFO = {
    "Andaman & Nicobar": ("AN", "Islands"), "Andaman and Nicobar Islands": ("AN", "Islands"),
    "Andhra Pradesh": ("AP", "South"),
    "Arunachal Pradesh": ("AR", "Northeast"), "Assam": ("AS", "Northeast"),
    "Bihar": ("BR", "East"), "Chandigarh": ("CH", "North"),
    "Chhattisgarh": ("CG", "Central"), "Chhatisgarh": ("CG", "Central"),
    "Dadra and Nagar Haveli and Daman and Diu": ("DD", "West"),
    "Delhi": ("DL", "North"), "Goa": ("GA", "West"), "Gujarat": ("GJ", "West"),
    "Haryana": ("HR", "North"), "Himachal Pradesh": ("HP", "North"),
    "Jammu & Kashmir": ("JK", "North"), "Jammu and Kashmir": ("JK", "North"),
    "Jharkhand": ("JH", "East"), "Karnataka": ("KA", "South"), "Kerala": ("KL", "South"),
    "Ladakh": ("LA", "North"), "Lakshadweep": ("LD", "Islands"),
    "Madhya Pradesh": ("MP", "Central"), "Maharashtra": ("MH", "West"),
    "Manipur": ("MN", "Northeast"), "Meghalaya": ("ML", "Northeast"), "Mizoram": ("MZ", "Northeast"),
    "Nagaland": ("NL", "Northeast"), "Odisha": ("OR", "East"),
    "Pondicherry": ("PY", "South"), "Puducherry": ("PY", "South"),
    "Punjab": ("PB", "North"), "Rajasthan": ("RJ", "North"), "Sikkim": ("SK", "Northeast"),
    "Tamil Nadu": ("TN", "South"), "Telangana": ("TG", "South"), "Tripura": ("TR", "Northeast"),
    "Uttar Pradesh": ("UP", "North"), "Uttarakhand": ("UK", "North"), "West Bengal": ("WB", "East"),
}

ZONE_COLOURS = {
    "North": "bg-sky-500",
    "South": "bg-emerald-500",
    "East": "bg-amber-500",
    "West": "bg-rose-500",
    "Central": "bg-violet-500",
    "Northeast": "bg-teal-500",
    "Islands": "bg-orange-500",
}

# Rows whose price should not be read at face value, with the reason. Shown next to the name.
SUSPECT_NOTES = {
    ("petrol", "global"): {
        "Hong Kong": "Octane 98, not 95",
        "Indonesia": "Far from a second source; check the fuel grade",
        "Malawi": "Not verified by an independent source",
    },
}


def country_code(name: str) -> str | None:
    return COUNTRY_CODES.get(name)


def append_history(key: str, rows: list[tuple[str, float]], retrieved_at: str) -> None:
    """Keep one snapshot per dataset per day, for future trend views."""
    history_dir = ROOT / "data" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"{key}.csv"
    day = retrieved_at[:10]
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            if any(record["date"] == day for record in csv.DictReader(handle)):
                return
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["date", "name", "price"])
        for name, price in rows:
            writer.writerow([day, name, f"{price:.3f}"])


# ---- Dataset registry -------------------------------------------------------

DATA_DIR = ROOT / "data" / "latest"
LOCAL_REFRESH = 3 * 3600  # Indian prices change daily; check every 3 hours
GLOBAL_REFRESH = 24 * 3600  # Country prices update weekly or monthly; check daily

DATASETS: list[Dataset] = [
    Dataset("petrol", "local", "INR", LOCAL_REFRESH, "Goodreturns (cross-checked with Cardekho)",
            make_local_fetch("petrol")),
    Dataset("diesel", "local", "INR", LOCAL_REFRESH, "Goodreturns (cross-checked with Cardekho)",
            make_local_fetch("diesel")),
    Dataset("crude", "local", "INR", LOCAL_REFRESH, "",
            fetch=None,
            note="India's crude basket price is not yet connected to a source that can be reused."),
    Dataset("petrol", "global", "USD", GLOBAL_REFRESH, "GlobalPetrolPrices",
            make_globalpetrol_fetch("petrol")),
    Dataset("diesel", "global", "USD", GLOBAL_REFRESH, "GlobalPetrolPrices",
            make_globalpetrol_fetch("diesel")),
    Dataset("kerosene", "global", "USD", GLOBAL_REFRESH, "GlobalPetrolPrices",
            make_globalpetrol_fetch("kerosene")),
    # Shown only when an EIA key is configured; without one the tab stays hidden.
    Dataset("crude", "global", "USD", GLOBAL_REFRESH, "EIA",
            fetch=make_eia_fetch() if eia_key() else None,
            unit_word="barrel"),
]
