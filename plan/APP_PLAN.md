# Fuelora: App Plan (Draft)

Status: draft. Research phase, no app code yet.

## Goal

A small open source app that shows current petrol prices:

- **India:** all 28 states and 8 union territories, with the price for each.
- **World:** one average petrol price per country, for the other countries.
- **Currency:** the user can choose the display currency.
- **Freshness:** each price shows the date it was retrieved, and the app says plainly when the data is stale.

Out of scope for now: diesel, CNG and other fuels (planned for a later phase).

## Requirements

| Area | Requirement |
|---|---|
| India data | 36 states/UTs, petrol only, one price per state/UT |
| World data | One national average per country, petrol (Octane-95 or nearest equivalent) |
| Freshness | Updated daily. Each record carries `as_of` and `retrieved_at` |
| Currency | User selects currency. Default INR for India, USD for world data |
| Averages | Labelled as simple (unweighted) averages unless a weighting is added |
| Open source | Code and data pipeline are public, with clear attribution to sources |

## Decisions still open

### 1. Data source (blocking)

This is the most important decision, because an open source app that republishes data can breach the source's terms.

- **Official oil-company data** (IOCL/BPCL/HPCL): IOCL's terms prohibit reproducing its content without written permission. Need permission for any automated or redistributed feed.
- **PPAC / data.gov.in:** likely the cleanest official source, but the datasets found so far are periodic, not daily.
- **Aggregators** (Goodreturns, Cardekho): usable for cross-checking, but terms usually restrict scraping and redistribution.

Recommended approach for an open source project:

1. **Do not commit scraped or licensed price data to the public repo.** Store only code and the source configuration.
2. **The app fetches from a source the user configures**, or ships with a clearly marked sample dataset.
3. **Seek written permission** from at least one OMC or confirm an open-data licence before any default live feed is included.

### 2. Currency conversion

- The world data is in USD, and India data is in INR. Converting between them needs exchange rates.
- Rates change daily, so they need the same freshness rules as fuel prices.
- Candidate: ECB daily reference rates (free, public). Check the reuse terms and attribution before use.
- The app should show the rate's date next to any converted figure.

### 3. Averages

- Current world average is a simple mean of national prices. It is not weighted by population or consumption.
- Decide whether to show a weighted version as well, and what weights to use.
- Averages should exclude countries with missing or suspicious data, and the app should say how many countries were included.

### 4. Country list

- Our 170-country list comes from GlobalPetrolPrices and has not been checked against a full reference list.
- Known gaps: Hong Kong is octane-98, not octane-95, so it should be shown separately or excluded from the average.
- Indonesia shows a large gap against a second source and needs a grade check.

### 5. Technology

Not chosen yet. Options:

- **Static site** with a JSON data file, rebuilt daily. Simplest to host and maintain.
- **Small backend** that fetches, caches and serves data. Needed if the data is licensed and must not be exposed to the browser.

Recommendation: start with a static site and a sample dataset, and add a fetch step only once the source is settled.

### 6. Scheduling

- Daily refresh, as discussed earlier. Its details depend on decision 1.

## Proposed structure

```
fuelora/
  data/
    sample/            # small, clearly labelled sample data for development
  plan/                # research, decisions, cross-checks (this folder)
  src/                 # app code (not yet created)
  scripts/             # fetch and validate scripts (not yet created)
  README.md
  LICENSE
```

## Next steps

1. Settle the data source (decision 1).
2. Choose the stack (decision 5).
3. Build a sample-data version of the app with currency selection and averages.
4. Add the daily fetch step once the source is confirmed.
