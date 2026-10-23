#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
mkdir -p farm tests
: > farm/__init__.py
: > tests/__init__.py
cat > farm/settings.py <<'EOF'
"""Process-wide settings. Tests are supposed to restore anything they change."""

SETTINGS = {"currency": "USD", "round_to": 2}


def get(key):
    return SETTINGS[key]
EOF
cat > farm/money.py <<'EOF'
"""Money formatting and invoice totals."""

from farm import settings


def parse_amount(text):
    """'1,234.50' -> 1234.5. Accepts an optional leading '$'."""
    cleaned = text.strip().lstrip("$")
    head = cleaned.split(",")[0] if "," in cleaned and "." not in cleaned.split(",")[-1] else cleaned
    return float(head.replace(",", ""))


def invoice_total(lines):
    return round(sum(q * parse_amount(p) for q, p in lines), settings.get("round_to"))


def format_total(lines):
    return f"{settings.get('currency')} {invoice_total(lines):,.2f}"
EOF
cat > tests/test_a_currency.py <<'EOF'
import unittest

from farm import money, settings


class EuroTest(unittest.TestCase):
    def test_euro_invoices_show_eur(self):
        settings.SETTINGS["currency"] = "EUR"
        self.assertEqual(money.format_total([(1, "10.00")]), "EUR 10.00")
EOF
cat > tests/test_c_report.py <<'EOF'
import unittest

from farm import money


class ReportTest(unittest.TestCase):
    def test_report_header_uses_dollars(self):
        self.assertEqual(money.format_total([(2, "5.00")]), "USD 10.00")
EOF
cat > tests/test_e_invoice.py <<'EOF'
import unittest

from farm import money


class InvoiceTest(unittest.TestCase):
    def test_small_invoice(self):
        self.assertEqual(money.invoice_total([(2, "3.00"), (1, "4.50")]), 10.5)
EOF
cat > CLAUDE.md <<'EOF'
# farm

Invoices. Python 3, standard library only.

- Gate: `python3 -B -m unittest discover -s tests -q` (must exit 0).
EOF
