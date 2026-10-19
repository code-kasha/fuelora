# Fuelora

Fuel price comparison for India and the world: petrol, diesel, kerosene and crude oil, by Indian state and by country, with currency conversion. An open-source personal research project that runs on your own computer.

> **Please note:** this is not an official source of fuel prices. Figures come from third-party sites and may differ from pump prices or from each other. The terms of use of those sites have not been reviewed for this project, so check them before reusing any data.

Research notes and decisions are in [`plan/`](plan/). The scraped data tables from that work are kept on the author's machine and are not part of this repository.

## Quick start

You need Python 3.10 or newer. Nothing else.

- **Windows (PowerShell):** `.\start.ps1`
  If Windows blocks it: `powershell -ExecutionPolicy Bypass -File .\start.ps1`
- **Linux / macOS:** `./start.sh` (not yet tested on either platform)

The script creates a private environment in `.venv` on the first run, fetches the latest prices, starts the server, and opens http://127.0.0.1:8000 in your browser. Press Ctrl+C to stop.

If the fetch fails (for example, no internet), the script warns you and shows the last saved prices.

### Run it manually

```
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python.exe
.venv/bin/python app/server.py                         # Windows: .venv\Scripts\python.exe app\server.py
```

`truststore` makes HTTPS use your operating system's certificate store. Without it, fetches can fail on some Windows and corporate networks.

## Features

- **Tabs** for petrol, diesel, kerosene and crude oil. A tab appears only when its data is available.
- **India / World** switch inside each tab.
- **Search** by state or country name.
- **Sort** by name, price, or distance from the average.
- **Currency** selector. Local prices are in rupees and world prices in US dollars; either can be converted.
- **Export CSV** of the current view, with the same filter, sort and currency.
- **State codes and zone dots** for India, with a legend. **Country flags** for the world view, loaded from flagcdn.com.
- **Cross-check badges.** Where Cardekho differs from Goodreturns by ₹1 or more, the state shows a "2nd source" badge with the second figure.
- **Check badges** on world rows that need care (for example, Hong Kong's octane 98 price).
- **Freshness badge:** "Today", "Yesterday", or how many days old the data is.
- **Dark / light mode** switch. It starts with your system setting and remembers your choice.

## Tabs and coverage

| Tab | India | World |
|---|---|---|
| Petrol | Yes, all 36 states and UTs | Yes, 170 countries |
| Diesel | Yes, all 36 states and UTs | Yes, 169 countries |
| Kerosene | Not offered (see Known limits) | Yes, 62 countries |
| Crude oil | Not offered | Brent and WTI, per barrel (needs an EIA key) |

Crude oil is shown per barrel, not per litre.

## How it stays current

- The page checks for new data every 5 minutes.
- India prices are refreshed at most every 3 hours, so a change in the daily price is picked up the same day.
- World prices are refreshed at most once a day. Each country's figure is updated by its source weekly or monthly, so a world price can be weeks old. The page shows the date for each dataset.
- If a refresh fails, the server keeps the last good data and the page says so.
- Fetched data is stored in `data/`, which is git-ignored. Nothing fetched is committed to the repo.
- One snapshot per day is saved in `data/history/` for future trend views.

## Crude oil (EIA key)

Crude prices come from the U.S. Energy Information Administration (EIA), which is free to use.

1. Register for a free key on the EIA Open Data page, https://www.eia.gov/opendata/ (use the Register link there).
2. Create a file named `.env` in the project root with one line: `EIA_API_KEY=your_key`.
3. Run `start.ps1` or `start.sh` again. The crude tab appears once the key is found.

The file is git-ignored, so the key is not committed. Keep it private: anyone with the key can use your EIA quota.

## License

MIT. See [LICENSE](LICENSE). The license covers this project's code only. It does not give rights to the third-party data the app fetches.

## Tests

```
python -m unittest discover -s tests
```

The tests use small synthetic snippets, so no third-party page is stored in the repo.

## Project layout

```
app/
  server.py       local web server, page and HTML fragments
  sources.py      data sources, parsers, state and country tables
  fx.py           ECB exchange rates and currency conversion
  static/         htmx (served locally)
start.ps1         Windows start script
start.sh          macOS / Linux start script (not yet tested)
tests/            offline parser tests
docs/index.html   static landing page (GitHub Pages), no price data
plan/             research notes and decisions
```

## Sources

- **India petrol and diesel:** [Goodreturns petrol](https://www.goodreturns.in/petrol-price.html) and [Goodreturns diesel](https://www.goodreturns.in/diesel-price.html). One request each per refresh.
- **India cross-check and Andhra Pradesh:** [Cardekho petrol](https://www.cardekho.com/petrol-price) and [Cardekho diesel](https://www.cardekho.com/diesel-price). One request each per refresh.
- **World petrol, diesel and kerosene:** [GlobalPetrolPrices](https://www.globalpetrolprices.com/gasoline_prices/), [diesel](https://www.globalpetrolprices.com/diesel_prices/) and [kerosene](https://www.globalpetrolprices.com/kerosene_prices/). One request each per refresh.
- **Crude oil:** [U.S. Energy Information Administration](https://www.eia.gov/opendata/), Brent (Europe spot) and WTI (Cushing spot).
- **Currency conversion:** [ECB daily reference rates](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml).

Converted figures are labelled with their source.

## Known limits

- **Kerosene in India** is set state by state through public distribution, and no single source covers every state. The app therefore shows kerosene for the world only.
- **Crude oil** shows Brent and WTI spot prices from EIA only. Indian crude basket prices are not connected. EIA data can lag several days, and the page shows the trading date for each benchmark.
- **World pairing:** GlobalPetrolPrices lists names and prices separately, so they are paired by their order on the page. The pairing is checked (the counts must match and the prices must ascend), but it isn't labelled in the markup. Spot-check a country before relying on it.
- **Andhra Pradesh** is missing from the Goodreturns tables, so it comes from Cardekho and is not cross-checked.
- **Prices are as reported by the sources.** Figures can differ by up to about ₹2 per state from other sites.
- **Hong Kong's petrol price** is for octane 98, since octane 95 isn't sold there. It carries a "Check" badge.
- **Terms of use were not checked.** The owner chose to skip this step. The terms of Goodreturns, Cardekho and GlobalPetrolPrices could not be fully verified, so review them before publishing anything beyond personal use.
- **Not tested on macOS or Linux.** `start.sh` has only been syntax-checked. The Windows script (`start.ps1`) has been tested.
