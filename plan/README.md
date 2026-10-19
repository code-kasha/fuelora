# Fuel Research: Petrol Prices (Research Phase)

Scope: **petrol only**. Diesel, CNG and other fuels are out of scope for now and will be added in a later phase.

## Files

| File | Contents |
|---|---|
| `india_petrol_by_state.csv` | Petrol price (₹/L) for all 28 states + 8 union territories |
| `world_petrol_by_country.csv` | Petrol price (USD/L) for 170 countries, one national average each |
| `README.md` | This file: method, sources, averages, caveats |

## Summary

### India (state-wise, ₹/L, as of 19 Oct 2026)
- States/UTs covered: **36 of 36** (Andhra Pradesh is a lower-confidence entry, see below)
- **Average: ₹106.54/L**
- Highest: Andhra Pradesh ₹118.08 (state average, Sep 2026), Telangana ₹116.15, Kerala ₹115.49
- Lowest: Andaman & Nicobar ₹88.66, Uttarakhand ₹99.54, Dadra/Nagar Haveli & Daman/Diu ₹99.44
- Delhi: ₹102.12

Variation between states comes mainly from state VAT and local levies. Central excise is the same everywhere.

### World (USD/L, Octane-95 gasoline, as of 12 Oct 2026)
- Countries: **170**
- **Simple average across countries: $1.596/L**
- Cheapest: Libya $0.023, Iran $0.029, Venezuela $0.035
- Most expensive: Hong Kong $4.424 (suspicious, see caveats), Norway $3.130, Malawi $3.226 (suspicious)
- India in the world table: **$1.144/L** (rank 34 of 170 from the bottom)

## Method

1. **India state-wise:** The Goodreturns table (dated 19 Oct 2026) was used as the primary source. It has 35 of 36 states/UTs. The missing one, Andhra Pradesh, was filled from The Core's NTR-district page, which quotes a state average of ₹118.08 dated 7 Sep 2026. That value is stale.
2. **World:** GlobalPetrolPrices.com gasoline table, dated 12 Oct 2026. The page lists countries and prices as separate lists, so each price was matched to its country by position. The India entry was checked: the country page shows $1.14/L, which matches the table's $1.144.
3. **Averages** were calculated with a simple (unweighted) mean. Population-weighted or volume-weighted averages would give different results.

## Cross-check results

Full details are in `crosscheck_india.csv` and `crosscheck_world.csv`.

**India (30 states/UTs with a second source, Cardekho, 19 Oct 2026)**
- Mean absolute difference: ₹0.62/L. Largest: Tamil Nadu ₹1.99 (primary ₹107.76 vs secondary ₹109.75).
- Three states differ by ₹1.5 or more: Tamil Nadu (₹1.99), Arunachal Pradesh (₹1.74), Bihar (₹1.69).
- On the same 30 states, the average is ₹107.09 (primary) vs ₹107.23 (secondary). The two sources agree closely on the average.
- Six states have no Cardekho figure: Andaman & Nicobar, Chhattisgarh, Goa, J&K, Ladakh, Lakshadweep. Those rest on a single source.

**World (22 countries with a second source, Trading Economics, Sep 2026)**
- Mean absolute difference: 6.1% excluding Indonesia, 10.0% including it.
- Indonesia is ~91% apart ($1.07 vs $0.56). Likely a fuel-grade difference (premium vs subsidised), not confirmed.
- 13 other countries differ by more than 3%. Largest: Mexico (+17%), China (+14%), Spain (−12%).
- Trading Economics is one month earlier (Sep vs Oct), so some of the gap is real price movement.
- Hong Kong and Malawi could not be checked against Trading Economics. The GlobalPetrolPrices country pages confirm both values, but that is the same provider, not an independent check. Hong Kong's figure is for octane-98 (octane-95 is not sold there), so it is not comparable with the other rows.

## Caveats

- **Date mismatch.** India data is dated 19 Oct 2026 and world data 12 Oct 2026. Rates change, so compare with that in mind.
- **Andhra Pradesh** is the only India row that is not from the 19 Oct table, and it is marked `low` confidence. Businesstoday shows ₹117.95 and ₹117.37, so the ₹118.08 figure is at the top of the range.
- **Hong Kong ($4.424)** is octane-98, not octane-95. Drop it or treat it separately. **Malawi ($3.226)** is confirmed by its country page, but not by an independent source.
- **Matching by position.** The world table was matched to countries by order. Eight of the 22 overlapping countries match within 3%, so the position-based mapping looks right for most rows, but treat any single row with caution.
- **Indonesia** is the largest outlier. Check the fuel grade before using it.
- **Single national figure per country.** Each country has one price. Countries with large regional variation (the US, India, Brazil) are represented by a single number that does not show that spread.
- **Sources differ.** The state-level prices in India differ by about ₹1–2 between aggregator sites. Official figures from IOCL, BPCL or HPCL should be used for anything published.
- **Source page average.** GlobalPetrolPrices states a world average of $1.47/L. Our simple average is $1.596. The difference comes from weighting and country coverage, not from a data error in our file.

## Sources

- India state-wise (primary): https://www.goodreturns.in/petrol-price.html (table dated 19 Oct 2026)
- India Andhra Pradesh: https://energy.thecore.in/fuel/petrol-price/ntr (state average, Sep 2026)
- India metro cross-check: https://english.punjabkesari.com/india/fuel-rates-today-petrol-diesel-price-breakdown-october-17-2026
- World gasoline prices: https://www.globalpetrolprices.com/gasoline_prices/ (dated 12 Oct 2026)

## Future work (not in this phase)

- Diesel, CNG and LPG prices by state and by country
- Refresh process: a dated snapshot per run, so trends can be tracked
- Confirm prices against official oil-company sources before an app launch
