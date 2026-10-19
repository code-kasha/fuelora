"""Local server for the Fuelora price page.

Serves the page and HTMX fragments from a cache. Each dataset is refreshed at most
once per its refresh interval, so however many browser polls arrive, the upstream
sites get one request per refresh.

Run from the repo root:  python app/server.py   then open http://127.0.0.1:8000
"""

import argparse
import csv
import datetime as dt
import html
import io
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow sibling imports when run as a script

try:  # use the OS certificate store; Python's bundled certs fail on some Windows/corporate networks
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    print("Warning: 'truststore' not installed; HTTPS may fail on some networks. Run: pip install -r requirements.txt")

from fx import convert, fetch_rates, read_rates  # noqa: E402
from sources import (  # noqa: E402
    CROSSCHECK_THRESHOLD, DATA_DIR, DATASETS, IST, STATE_INFO, SUSPECT_NOTES, ZONE_COLOURS, Dataset,
    append_history, country_code, read_rows,
)

APP_DIR = Path(__file__).resolve().parent
FX_JSON = DATA_DIR / "fx_rates.json"
FX_REFRESH_SECONDS = 3 * 3600
HOST, PORT = "127.0.0.1", 8000

FUELS = [("petrol", "Petrol"), ("diesel", "Diesel"), ("kerosene", "Kerosene"), ("crude", "Crude oil")]
SCOPES = [("local", "India"), ("global", "World")]
PREFERRED_CURRENCIES = ["INR", "USD"]

# Sort fields. To add one: add an entry here and a matching branch in sort_rows().
SORTS = [
    ("name_asc", "Name: A → Z"),
    ("name_desc", "Name: Z → A"),
    ("price_asc", "Price: low → high"),
    ("price_desc", "Price: high → low"),
    ("above_avg", "Most above average"),
    ("below_avg", "Most below average"),
]

_lock = threading.Lock()
_last_error: dict[str, str] = {}


def _age(path: Path) -> float:
    return time.time() - path.stat().st_mtime if path.exists() else float("inf")


def refresh_if_stale(force: bool = False) -> None:
    """Refetch each dataset older than its refresh interval (or all, if forced).

    Keeps the old cache on failure, records the error for the page, and adds a
    daily snapshot to the history folder after each successful fetch.
    """
    with _lock:
        for dataset in DATASETS:
            if dataset.fetch is None:
                continue
            if force or _age(dataset.path) > dataset.refresh_seconds:
                try:
                    dataset.fetch(dataset.path)
                    _last_error.pop(dataset.key, None)
                    rows, retrieved_at = read_rows(dataset.path)
                    append_history(dataset.key, rows, retrieved_at)
                except Exception as exc:  # noqa: BLE001 - any failure should keep the cache
                    _last_error[dataset.key] = str(exc)
        if force or _age(FX_JSON) > FX_REFRESH_SECONDS:
            try:
                fetch_rates(FX_JSON, dt.datetime.now(IST).isoformat(timespec="minutes"))
                _last_error.pop("fx", None)
            except Exception as exc:  # noqa: BLE001
                _last_error["fx"] = str(exc)


def load_rates() -> dict[str, float]:
    return read_rates(FX_JSON) if FX_JSON.exists() else {}


def find_dataset(fuel: str, scope: str) -> Dataset | None:
    return next((d for d in DATASETS if d.fuel == fuel and d.scope == scope), None)


def live_scopes(fuel: str) -> list[str]:
    """Scopes that have a working data source for this fuel."""
    return [d.scope for d in DATASETS if d.fuel == fuel and d.fetch is not None]


def live_fuels() -> list[tuple[str, str]]:
    """Fuel tabs to show: only fuels with at least one working data source."""
    return [(key, label) for key, label in FUELS if live_scopes(key)]


def sort_rows(rows: list[tuple[str, float]], sort: str, average: float) -> list[tuple[str, float]]:
    if sort == "name_desc":
        return sorted(rows, key=lambda r: r[0].lower(), reverse=True)
    if sort == "price_asc":
        return sorted(rows, key=lambda r: r[1])
    if sort == "price_desc":
        return sorted(rows, key=lambda r: r[1], reverse=True)
    if sort == "above_avg":
        return sorted(rows, key=lambda r: r[1] - average, reverse=True)
    if sort == "below_avg":
        return sorted(rows, key=lambda r: r[1] - average)
    return sorted(rows, key=lambda r: r[0].lower())  # name_asc, the default


def filter_rows(rows: list[tuple[str, float]], query: str) -> list[tuple[str, float]]:
    query = query.strip().lower()
    return [row for row in rows if not query or query in row[0].lower()]


def format_amount(value: float, code: str) -> str:
    symbols = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
    if code in symbols:
        return f"{symbols[code]}{value:,.2f}"
    return f"{value:,.2f} {code}"


def currency_choices(rates: dict[str, float]) -> list[str]:
    preferred = [code for code in PREFERRED_CURRENCIES if code in rates]
    return preferred + sorted(code for code in rates if code not in preferred)


def view_url(fuel: str, scope: str, currency: str, sort: str, query: str = "") -> str:
    params = {"fuel": fuel, "scope": scope, "currency": currency, "sort": sort}
    if query:
        params["q"] = query
    return "/view?" + urlencode(params)


def cross_check_prices(dataset: Dataset) -> dict[str, float]:
    """Second-source prices for the same states, if a cross-check file exists."""
    if dataset.scope != "local":
        return {}
    path = DATA_DIR / f"{dataset.fuel}_local_check.csv"
    if not path.exists():
        return {}
    rows, _ = read_rows(path)
    return dict(rows)


def freshness(retrieved_at: str) -> tuple[str, str]:
    """Return (label, colour name) describing how old the data is."""
    day = dt.datetime.fromisoformat(retrieved_at).astimezone(IST).date()
    gap = (dt.datetime.now(IST).date() - day).days
    if gap <= 0:
        return "Today", "emerald"
    if gap == 1:
        return "Yesterday", "amber"
    return f"{gap} days old", "rose"


def flag_html(name: str, scope: str) -> str:
    """A country flag for the world view, or a state code with a zone dot for India."""
    if scope == "local":
        return state_code_html(name)
    code = country_code(name)
    if not code:
        return '<span class="inline-block w-5 shrink-0" aria-hidden="true"></span>'
    return (f'<img src="https://flagcdn.com/w40/{code}.png" alt="" width="20" height="14" loading="lazy" '
            f'class="h-3.5 w-5 shrink-0 rounded-sm object-cover ring-1 ring-black/10">')


def state_code_html(name: str) -> str:
    info = STATE_INFO.get(name)
    if not info:
        return '<span class="inline-block w-9 shrink-0" aria-hidden="true"></span>'
    code, zone = info
    return (f'<span class="flex w-12 shrink-0 items-center gap-1.5" title="{html.escape(name)} · {zone} zone">'
            f'<span class="h-2 w-2 shrink-0 rounded-full {ZONE_COLOURS[zone]}" aria-hidden="true"></span>'
            f'<span class="rounded bg-slate-100 px-1 font-mono text-[11px] font-semibold tracking-wide text-slate-600 '
            f'dark:bg-slate-800 dark:text-slate-300">{code}</span></span>')


def zone_legend_html() -> str:
    items = "".join(
        f'<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full {colour}" aria-hidden="true"></span>{zone}</span>'
        for zone, colour in ZONE_COLOURS.items()
    )
    return f'<div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">{items}</div>'


def render_empty(message: str) -> str:
    return (f'<div class="rounded-xl bg-slate-50 p-6 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">'
            f'<p class="font-medium text-slate-800 dark:text-slate-100">Not available yet</p>'
            f'<p class="mt-2 text-sm">{html.escape(message)}</p></div>')


def _tile(label: str, value: str, sub: str, value_class: str = "") -> str:
    return (f'<div class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60">'
            f'<p class="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>'
            f'<p class="mt-1 text-lg font-semibold tabular-nums {value_class}">{value}</p>'
            f'<p class="truncate text-xs text-slate-500 dark:text-slate-400">{sub}</p></div>')


def render_body(dataset: Dataset, currency: str, sort: str, rates: dict[str, float], query: str) -> tuple[str, str]:
    """Return (body_html, status_html) for one dataset."""
    if dataset.fetch is None:
        return render_empty(dataset.note), ""
    try:
        rows, retrieved_at = read_rows(dataset.path)
    except (FileNotFoundError, KeyError, IndexError):
        return render_empty("No data yet. Check your internet connection and restart the server."), ""

    def show(price: float) -> float:
        return convert(price, rates, dataset.unit, currency) if currency != dataset.unit else price

    def money(price: float) -> str:
        return format_amount(show(price), currency)

    average = sum(price for _, price in rows) / len(rows)
    lowest = min(rows, key=lambda r: r[1])
    highest = max(rows, key=lambda r: r[1])
    span = (highest[1] - lowest[1]) or 1.0
    if dataset.fuel == "crude":
        average_label, unit_label, item_label = "Benchmark average", "benchmarks (simple average)", "Benchmark"
    elif dataset.scope == "local":
        average_label, unit_label, item_label = "India average", "states and UTs", "State / UT"
    else:
        average_label, unit_label, item_label = "World average", "countries (simple average)", "Country"

    tiles = f"""
<div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
  {_tile(average_label, money(average), f"{len(rows)} {unit_label}")}
  {_tile("Lowest", money(lowest[1]), html.escape(lowest[0]), "text-emerald-600 dark:text-emerald-400")}
  {_tile("Highest", money(highest[1]), html.escape(highest[0]), "text-rose-600 dark:text-rose-400")}
  {_tile("Spread", format_amount(show(highest[1]) - show(lowest[1]), currency), "highest minus lowest")}
</div>"""

    checks = cross_check_prices(dataset)
    visible = filter_rows(rows, query)
    items = []
    for name, price in sort_rows(visible, sort, average):
        diff = show(price) - show(average)
        diff_class = "text-rose-600 dark:text-rose-400" if diff > 0 else "text-emerald-600 dark:text-emerald-400"
        bar = (price - lowest[1]) / span * 100

        badges = []
        note = SUSPECT_NOTES.get((dataset.fuel, dataset.scope), {}).get(name)
        if note:
            badges.append(f'<span title="{html.escape(note)}" class="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 '
                          f'text-[10px] font-medium text-amber-800 dark:bg-amber-900/60 dark:text-amber-200">Check</span>')
        other = checks.get(name)
        if other is not None and abs(other - price) >= CROSSCHECK_THRESHOLD:
            badges.append(f'<span title="Second source (Cardekho): ₹{other:,.2f}" class="shrink-0 rounded bg-sky-100 '
                          f'px-1.5 py-0.5 text-[10px] font-medium text-sky-800 dark:bg-sky-900/60 dark:text-sky-200">'
                          f'2nd source ₹{other:,.2f}</span>')

        items.append(
            '<li class="flex flex-col gap-2 bg-white px-4 py-3 dark:bg-slate-900">'
            '<div class="flex items-baseline justify-between gap-3">'
            f'<span class="flex min-w-0 items-center gap-2">{flag_html(name, dataset.scope)}'
            f'<span class="truncate font-medium">{html.escape(name)}</span>{"".join(badges)}</span>'
            f'<span class="shrink-0 font-semibold tabular-nums">{money(price)}</span></div>'
            '<div class="flex items-center gap-3">'
            '<div class="h-1.5 flex-1 rounded-full bg-slate-100 dark:bg-slate-800">'
            f'<div class="h-1.5 rounded-full bg-gradient-to-r from-amber-400 to-rose-500" style="width:{bar:.0f}%"></div></div>'
            f'<span class="w-20 shrink-0 text-right text-sm tabular-nums {diff_class}">{diff:+,.2f}</span></div>'
            '</li>'
        )
    if not items:
        items.append(f'<li class="bg-white px-4 py-6 text-sm text-slate-500 dark:bg-slate-900 dark:text-slate-400">'
                     f'No matches for “{html.escape(query)}”.</li>')

    # Fixed-height list that scrolls inside its box. Two columns on medium and larger screens.
    table = f"""
<div class="mt-6 overflow-hidden rounded-xl ring-1 ring-slate-200 dark:ring-slate-800">
  <div class="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
    <span>{item_label} · per {dataset.unit_word}</span>
    <span>vs average</span>
  </div>
  <ul class="thin-scroll grid h-[26rem] grid-cols-1 content-start gap-px overflow-y-auto bg-slate-200 md:grid-cols-2 dark:bg-slate-800">{''.join(items)}</ul>
</div>"""

    label, colour = freshness(retrieved_at)
    when = dt.datetime.fromisoformat(retrieved_at).strftime("%d %b %Y, %H:%M")
    status_bits = [f"Prices as of {when} IST", f"Source: {html.escape(dataset.source_name)}"]
    if dataset.fuel == "crude":
        status_bits.append("Unit: US dollars per barrel, not per litre")
    if currency != dataset.unit:
        status_bits.append(f"Converted from {dataset.unit} at ECB rates")
    status = (f'<p class="mt-5 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">'
              f'<span class="rounded-full bg-{colour}-100 px-2 py-0.5 font-medium text-{colour}-800 '
              f'dark:bg-{colour}-900/60 dark:text-{colour}-200">{label}</span>'
              f'{" · ".join(status_bits)}</p>')
    if dataset.scope == "local":
        status += zone_legend_html()
    return tiles + table, status


def render_panel(fuel: str, scope: str, currency: str, sort: str, query: str = "") -> str:
    fuels = live_fuels()
    fuel = fuel if fuel in dict(fuels) else fuels[0][0]
    scope = scope if scope in dict(SCOPES) else "local"
    sort = sort if sort in dict(SORTS) else "name_asc"
    query = query.strip()[:80]
    rates = load_rates()
    available = live_scopes(fuel)
    if scope not in available:
        scope = available[0]
    dataset = find_dataset(fuel, scope)
    if dataset is None:
        return render_empty("This view is not set up.")
    if currency not in rates and currency != dataset.unit:
        currency = dataset.unit
    choices = currency_choices(rates) or [dataset.unit]
    if currency not in choices:
        choices = [dataset.unit] + choices

    body, status = render_body(dataset, currency, sort, rates, query)
    warnings = "".join(
        f'<div class="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">'
        f'{html.escape(key)} refresh failed: {html.escape(msg)}</div>'
        for key, msg in _last_error.items() if key in (dataset.key, "fx")
    )

    focus = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
    fuel_tabs = "".join(
        f'<button type="button" aria-pressed="{str(key == fuel).lower()}" '
        f'hx-get="{view_url(key, scope, currency, sort, query)}" hx-target="#panel" hx-swap="outerHTML" '
        f'class="rounded-full px-4 py-1.5 text-sm font-medium transition {focus} '
        f'{"bg-slate-900 text-white shadow dark:bg-amber-400 dark:text-slate-900" if key == fuel else "text-slate-600 hover:bg-slate-200/70 dark:text-slate-300 dark:hover:bg-slate-800"}">'
        f'{label}</button>'
        for key, label in fuels
    )
    scope_tabs = "".join(
        f'<button type="button" aria-pressed="{str(key == scope).lower()}" '
        f'hx-get="{view_url(fuel, key, currency, sort, query)}" hx-target="#panel" hx-swap="outerHTML" '
        f'class="rounded-md px-3 py-1 text-sm transition {focus} '
        f'{"bg-white font-semibold text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white" if key == scope else "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"}">'
        f'{label}</button>'
        for key, label in SCOPES if key in available
    )
    # The India/World switch only appears for fuels that have both views.
    scope_switch = ""
    if len(available) > 1:
        scope_switch = f'<div class="flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800/70">{scope_tabs}</div>'
    currency_options = "".join(
        f'<option value="{code}"{" selected" if code == currency else ""}>{code}</option>' for code in choices
    )
    sort_options = "".join(
        f'<option value="{key}"{" selected" if key == sort else ""}>{label}</option>' for key, label in SORTS
    )
    select_class = (f"rounded-lg border-slate-300 bg-white py-2 pl-3 pr-8 text-sm shadow-sm {focus} "
                    "dark:border-slate-700 dark:bg-slate-800")
    export_url = "/export.csv?" + urlencode({"fuel": fuel, "scope": scope, "currency": currency,
                                              "sort": sort, "q": query})

    return f"""
<div id="panel" class="contents"
     hx-get="{view_url(fuel, scope, currency, sort, query)}" hx-trigger="every 5m" hx-swap="outerHTML">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap gap-1 rounded-full bg-slate-100 p-1 dark:bg-slate-800/70">{fuel_tabs}</div>
    {scope_switch}
  </div>

  <form class="mt-5 flex flex-wrap items-end gap-3" hx-get="/view" hx-target="#panel" hx-swap="outerHTML" hx-trigger="change">
    <input type="hidden" name="fuel" value="{fuel}">
    <input type="hidden" name="scope" value="{scope}">
    <label class="flex min-w-[12rem] flex-1 flex-col text-xs font-medium text-slate-500 dark:text-slate-400">Search
      <input type="search" name="q" value="{html.escape(query)}" placeholder="Type a name"
             class="mt-1 {select_class}"
             hx-get="/view" hx-include="closest form" hx-target="#panel" hx-swap="outerHTML"
             hx-trigger="input changed delay:300ms">
    </label>
    <label class="flex flex-col text-xs font-medium text-slate-500 dark:text-slate-400">Sort by
      <select name="sort" class="mt-1 {select_class}">{sort_options}</select>
    </label>
    <label class="flex flex-col text-xs font-medium text-slate-500 dark:text-slate-400">Currency
      <select name="currency" class="mt-1 {select_class}">{currency_options}</select>
    </label>
    <a href="{export_url}" class="mt-1 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 {focus} dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">Export CSV</a>
  </form>

  <div class="mt-6">{body}</div>
  {status}
  {warnings}
</div>"""


def export_csv(fuel: str, scope: str, currency: str, sort: str, query: str) -> str:
    """The current view as CSV: the same names, filter, sort and currency as on screen."""
    dataset = find_dataset(fuel, scope)
    if dataset is None or dataset.fetch is None:
        return "name,price,currency\n"
    rates = load_rates()
    if currency != dataset.unit and currency not in rates:
        currency = dataset.unit
    rows, _ = read_rows(dataset.path)
    average = sum(price for _, price in rows) / len(rows)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "price", "currency"])
    decimals = 3 if dataset.unit == "USD" else 2  # world prices are often below one cent per litre
    for name, price in sort_rows(filter_rows(rows, query), sort, average):
        value = convert(price, rates, dataset.unit, currency) if currency != dataset.unit else price
        writer.writerow([name, f"{value:.{decimals}f}", currency])
    return output.getvalue()


def render_page() -> str:
    panel = render_panel("petrol", "local", "INR", "name_asc")
    return f"""<!doctype html>
<html lang="en" class="h-full">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fuelora · Fuel prices</title>
  <script>
    // Apply the saved theme before the page paints, so there is no flash.
    (function () {{
      var saved = localStorage.getItem("fuelora-theme");
      var dark = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
      document.documentElement.classList.toggle("dark", dark);
    }})();
    function toggleTheme() {{
      var root = document.documentElement;
      var dark = root.classList.toggle("dark");
      localStorage.setItem("fuelora-theme", dark ? "dark" : "light");
    }}
  </script>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>tailwind.config = {{ darkMode: "class" }};</script>
  <script src="/static/htmx.min.js"></script>
  <style>
    /* Thin, quiet scrollbars for the country and state lists. */
    .thin-scroll {{ scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent; }}
    .thin-scroll::-webkit-scrollbar {{ width: 8px; }}
    .thin-scroll::-webkit-scrollbar-track {{ background: transparent; }}
    .thin-scroll::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 9999px; }}
    .thin-scroll::-webkit-scrollbar-thumb:hover {{ background: #94a3b8; }}
    .dark .thin-scroll {{ scrollbar-color: #475569 transparent; }}
    .dark .thin-scroll::-webkit-scrollbar-thumb {{ background: #475569; }}
    .dark .thin-scroll::-webkit-scrollbar-thumb:hover {{ background: #64748b; }}
  </style>
</head>
<body class="min-h-full bg-gradient-to-br from-slate-100 via-white to-amber-50 text-slate-900 antialiased dark:from-slate-950 dark:via-slate-900 dark:to-slate-950 dark:text-slate-100">
  <main class="mx-auto w-[80vw] px-4 py-10 sm:px-6">
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div class="flex flex-col gap-2">
        <p class="text-sm font-medium uppercase tracking-widest text-amber-600 dark:text-amber-400">Fuelora</p>
        <h1 class="text-3xl font-bold tracking-tight sm:text-4xl">Fuel prices</h1>
        <p class="text-slate-600 dark:text-slate-400">Fuel prices for India and the world.</p>
      </div>
      <button type="button" onclick="toggleTheme()" aria-label="Switch between dark and light mode"
              class="rounded-full border border-slate-300 bg-white/80 px-4 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200">
        <span class="dark:hidden">Dark mode</span><span class="hidden dark:inline">Light mode</span>
      </button>
    </header>

    <section class="mt-8 rounded-2xl bg-white/80 p-5 shadow-xl shadow-slate-200/60 ring-1 ring-slate-200 backdrop-blur sm:p-7 dark:bg-slate-900/80 dark:shadow-none dark:ring-slate-800">
      {panel}
    </section>

    <footer class="mt-8 text-center text-xs text-slate-500">
      <p class="font-medium text-slate-600 dark:text-slate-400">Akash Damle. 2026.</p>
      <p class="mt-1">Data from Goodreturns, GlobalPetrolPrices and EIA · currency from ECB · not an official source</p>
    </footer>
  </main>
</body>
</html>"""


class _Server(ThreadingHTTPServer):
    # On Windows, address reuse lets a second server bind the same port and split requests.
    # Turning it off makes a second start fail clearly instead.
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        content_type = "text/html; charset=utf-8"
        extra_headers: list[tuple[str, str]] = []

        if url.path == "/":
            refresh_if_stale()
            body, status = render_page(), 200
        elif url.path == "/view":
            refresh_if_stale()
            body = render_panel(
                query.get("fuel", "petrol"),
                query.get("scope", "local"),
                query.get("currency", "INR"),
                query.get("sort", "name_asc"),
                query.get("q", ""),
            )
            status = 200
        elif url.path == "/export.csv":
            refresh_if_stale()
            body = export_csv(
                query.get("fuel", "petrol"),
                query.get("scope", "local"),
                query.get("currency", "INR"),
                query.get("sort", "name_asc"),
                query.get("q", ""),
            )
            content_type = "text/csv; charset=utf-8"
            extra_headers.append(("Content-Disposition",
                                  f'attachment; filename="fuelora_{query.get("fuel", "petrol")}_'
                                  f'{query.get("scope", "local")}.csv"'))
            status = 200
        elif url.path == "/static/htmx.min.js":
            body = (APP_DIR / "static" / "htmx.min.js").read_text(encoding="utf-8")
            content_type = "application/javascript; charset=utf-8"
            status = 200
        else:
            body, status = "<h1>Not found</h1>", 404

        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for name, value in extra_headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # keep the console quiet apart from errors
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Fuelora fuel price server")
    parser.add_argument("--fetch-only", action="store_true",
                        help="fetch fresh prices now, then exit (used by the start scripts)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if args.fetch_only:
        refresh_if_stale(force=True)
        if _last_error:
            for key, msg in _last_error.items():
                print(f"Fetch failed ({key}): {msg}")
            sys.exit(1)
        print("Latest prices fetched.")
        return

    refresh_if_stale()
    server = _Server((HOST, PORT), Handler)
    print(f"Fuelora running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
