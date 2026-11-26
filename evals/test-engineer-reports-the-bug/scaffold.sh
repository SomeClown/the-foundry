#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
mkdir -p shop tests
: > shop/__init__.py
: > tests/__init__.py
cat > shop/pricing.py <<'EOF'
"""Order totals, in whole cents."""

DISCOUNT_FROM_CENTS = 10000
DISCOUNT_PERCENT = 10


def order_total(subtotal_cents, shipping_cents=0):
    """Total to charge, in cents.

    Orders of $100.00 or more (subtotal_cents >= 10000) get 10% off the
    subtotal, rounded down to the cent. Shipping is never discounted.
    A negative subtotal or shipping raises ValueError.
    """
    if subtotal_cents < 0 or shipping_cents < 0:
        raise ValueError("amounts can't be negative")
    if subtotal_cents > DISCOUNT_FROM_CENTS:
        subtotal_cents -= subtotal_cents * DISCOUNT_PERCENT // 100
    return subtotal_cents + shipping_cents
EOF
cat > tests/test_smoke.py <<'EOF'
import unittest

from shop.pricing import order_total


class SmokeTest(unittest.TestCase):
    def test_small_order_pays_full_price_plus_shipping(self):
        self.assertEqual(order_total(5000, 500), 5500)
EOF
cat > CLAUDE.md <<'EOF'
# shop

Order totals for a small shop. Python 3, standard library only.

- Gate: `python3 -B -m unittest discover -s tests -q` (must exit 0).
- Tests use the standard library's `unittest` and live in `tests/`.
EOF
