# Fuelora

Fuel price comparison for India and the world: petrol, diesel, kerosene and crude oil, by Indian state and by country, with currency conversion. An open-source personal research project that runs on your own computer.

> **Please note:** this is not an official source of fuel prices. Figures come from third-party sites and may differ from pump prices or from each other. The terms of use of those sites have not been reviewed for this project, so check them before reusing any data.

Research notes, source checks and decisions are in [`plan/`](plan/).

## Quick start

You need Python 3.10 or newer. Nothing else.

- **Windows (PowerShell):** `.\start.ps1`
  If Windows blocks it: `powershell -ExecutionPolicy Bypass -File .\start.ps1`
- **Linux / macOS:** `./start.sh`

The script creates a private environment in `.venv` on the first run, fetches the latest prices, starts the server, and opens http://127.0.0.1:8000 in your browser. Press Ctrl+C to stop.

If the fetch fails (for example, no internet), the script warns you and shows the last saved prices.

## Run it manually

```
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv\Scripts\python.exe
.venv/bin/python app/server.py                         # Windows: .venv\Scripts\python.exe app\server.py
```

`truststore` makes HTTPS use your operating system's certificate store. Without it, fetches can fail on some Windows and corporate networks.

## How it stays current

- The page polls the local server every 5 minutes.
- The server refreshes its data from the source at most once every 3 hours, however often the page is opened. Oil companies revise prices at about 6 AM IST, so the first page load after that shows the new prices.
- If a refresh fails, the server keeps the last good data and the page says so.
- Data is stored in `data/latest/`, which is git-ignored. Nothing fetched is committed to the repo.

## Features

- **Search** by state or country name.
- **Export CSV** of the current view, with the same filter, sort and currency.
- **Dark / light mode** switch. It starts with your system setting and remembers your choice.
- **Flags** for each country in the world view.
- **Cross-check flags.** Where Cardekho differs from Goodreturns by ₹1 or more, the state shows a "2nd source" badge with the second figure.
- **Check flags** on world rows that need care (for example, Hong Kong's octane 98 price).
- **Freshness badge:** "Today", "Yesterday", or how many days old the data is.
- **History:** one snapshot per day is saved in `data/history/` for future trend views.

## Tabs

- **Petrol, Diesel, Kerosene, Crude oil** across the top.
- **India / World** switch inside each tab.

| Tab | India | World |
|---|---|---|
| Petrol | Yes, 35 of 36 states and UTs | Yes, 170 countries |
| Diesel | Yes, 35 of 36 states and UTs | Yes, 169 countries |
| Kerosene | Not offered (see below) | Yes, 62 countries |
| Crude oil | Not offered (see below) | Brent and WTI, per barrel (needs an EIA key) |

A tab appears only when its data is available. Crude oil is hidden until an EIA key is set up.

## Tests

```
python -m unittest discover -s tests
```

The tests use small synthetic snippets, so no third-party page is stored in the repo.

## Crude oil (EIA key)

Crude prices come from the U.S. Energy Information Administration (EIA), which is free to use.

1. Register for a free key on the EIA Open Data page, https://www.eia.gov/opendata/ (use the Register link there).
2. Create a file named `.env` in the project root with one line: `EIA_API_KEY=your_key`.
3. Run `start.ps1` or `start.sh` again. The crude tab appears once the key is found.

The file is git-ignored, so the key is not committed. Keep it private: anyone with the key can use your EIA quota.

## How it stays current

- The page checks for new data every 5 minutes.
- India prices are refreshed at most every 3 hours, so a change after the daily revision is picked up the same day.
- World prices are refreshed at most once a day. Each country's figure is updated by its source weekly or monthly, so a world price can be weeks old. The page shows the date for each dataset.
- If a refresh fails, the server keeps the last good data and the page says so.
- Data is stored in `data/latest/`, which is git-ignored. Nothing fetched is committed to the repo.

## Sources

- **India petrol and diesel:** [Goodreturns petrol](https://www.goodreturns.in/petrol-price.html) and [Goodreturns diesel](https://www.goodreturns.in/diesel-price.html). One request each per refresh.
- **World petrol, diesel and kerosene:** [GlobalPetrolPrices](https://www.globalpetrolprices.com/gasoline_prices/), [diesel](https://www.globalpetrolprices.com/diesel_prices/) and [kerosene](https://www.globalpetrolprices.com/kerosene_prices/). One request each per refresh.
- **Currency conversion:** [ECB daily reference rates](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml).

Converted figures are labelled with their source. Local prices are in rupees and world prices in US dollars, and you can convert either to another currency.

## Known limits

- **Andhra Pradesh is not on either Goodreturns table**, so the India views show 35 of 36 states and UTs.
- **Kerosene in India** is set state by state through public distribution, and I found no single source for it. The app therefore shows kerosene for the world only.
- **Crude oil** shows the Brent and WTI spot prices from EIA only. Indian crude basket prices are not connected yet. The EIA's latest data can lag several days behind today, and the page shows the trading date for each benchmark.
- **World pairing:** GlobalPetrolPrices shows names and prices separately, so they are paired by their order on the page. The pairing is checked (the counts must match and the prices must ascend), but it is not labelled in the markup. Spot-check a country before relying on it.
- **Terms of use were not checked.** The owner chose to skip this step. Goodreturns' and GlobalPetrolPrices' terms could not be fully verified, so review them before publishing anything beyond personal use.
- **Not tested on macOS or Linux.** `start.sh` has only been syntax-checked. The Windows script (`start.ps1`) has been tested.
- **Prices are as reported by the sources.** Figures can differ by up to about ₹2 per state from other sites.
- **Hong Kong's petrol price** is for octane 98, since octane 95 isn't sold there. The table shows it without a note.
