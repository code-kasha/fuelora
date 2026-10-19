"""Offline tests for the parsers. They use small synthetic snippets, not saved third-party pages.

Run from the repo root:  python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from sources import (  # noqa: E402
    latest_crude_rows, parse_cardekho, parse_globalpetrol, parse_goodreturns,
)


def goodreturns_page(rows: int) -> str:
    body = "".join(
        f'<tr><td><a href="/x.html" title="S{i}">S{i}</a></td><td>&#x20b9;{90 + i}.50</td>'
        f'<td><span class="fp-flat">0.00</span></td></tr>'
        for i in range(rows)
    )
    return f'<table class="gr-table"><thead><tr><th>State</th><th>Price</th></tr></thead><tbody>{body}</tbody></table>'


def globalpetrol_page(names: list[str], prices: list[str]) -> str:
    links = "".join(f"<a class='graph_outside_link'>{n}&nbsp;</a>" for n in names)
    labels = "".join(f'<div style="color: #000000;">{p}</div>' for p in prices)
    return f"<div id='outsideLinks'>{links}</div><div id='graphic'>{labels}</div>"


def cardekho_page(rows: list[tuple[str, str]]) -> str:
    body = "".join(f"<tr><td>{n}</td><td>{p}</td></tr>" for n, p in rows)
    return f"<table><tbody><tr></tr><tr><td>State</td><td>Price (cost/L)</td></tr>{body}</tbody></table>"


class GoodreturnsTests(unittest.TestCase):
    def test_reads_state_rows(self):
        rows = parse_goodreturns(goodreturns_page(34))
        self.assertEqual(len(rows), 34)
        self.assertEqual(rows[0], ("S0", 90.5))

    def test_rejects_too_few_rows(self):
        with self.assertRaises(ValueError):
            parse_goodreturns(goodreturns_page(10))


class GlobalPetrolTests(unittest.TestCase):
    def test_pairs_names_and_prices_in_order(self):
        page = globalpetrol_page(["Libya", "Iran*"], ["0.023", "0.029"])
        self.assertEqual(parse_globalpetrol(page), [("Libya", 0.023), ("Iran", 0.029)])

    def test_refuses_mismatched_counts(self):
        with self.assertRaises(ValueError):
            parse_globalpetrol(globalpetrol_page(["Libya", "Iran"], ["0.023"]))

    def test_refuses_non_ascending_prices(self):
        with self.assertRaises(ValueError):
            parse_globalpetrol(globalpetrol_page(["Libya", "Iran"], ["0.5", "0.1"]))


class CardekhoTests(unittest.TestCase):
    def test_skips_empty_row_and_maps_aliases(self):
        rows = [("Andhra Pradesh", "₹117.61"), ("Puducherry", "₹103.45")] + [
            (f"State {i}", f"₹{90 + i}") for i in range(30)
        ]
        parsed = parse_cardekho(cardekho_page(rows))
        self.assertEqual(parsed[0], ("Andhra Pradesh", 117.61))
        self.assertEqual(parsed[1], ("Pondicherry", 103.45))
        self.assertEqual(len(parsed), 32)

    def test_missing_table_raises(self):
        with self.assertRaises(ValueError):
            parse_cardekho("<table><tr><td>Other</td><td>1</td></tr></table>")


class CrudeTests(unittest.TestCase):
    def test_takes_latest_non_empty_value_per_benchmark(self):
        records = [
            {"product": "EPCBRENT", "period": "2026-10-14", "value": None},
            {"product": "EPCWTI", "period": "2026-10-14", "value": "101.91"},
            {"product": "EPCBRENT", "period": "2026-10-13", "value": "125.78"},
            {"product": "EPCWTI", "period": "2026-10-13", "value": "100.86"},
        ]
        rows = latest_crude_rows(records)
        self.assertEqual(rows[0], ("Brent crude (Europe spot) · 2026-10-13", 125.78))
        self.assertEqual(rows[1], ("WTI crude (Cushing spot) · 2026-10-14", 101.91))

    def test_missing_benchmark_raises(self):
        with self.assertRaises(ValueError):
            latest_crude_rows([{"product": "EPCWTI", "period": "2026-10-14", "value": "101.91"}])


if __name__ == "__main__":
    unittest.main()
