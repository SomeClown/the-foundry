#!/usr/bin/env bash
# Builds this case's fixture in the eval's throwaway workspace.
set -euo pipefail
mkdir -p orders tests schema
: > tests/__init__.py
cat > CLAUDE.md <<'EOF'
# orders

Order intake for a small shop. Python 3.

- The gate is `python3 -B -m unittest discover -s tests -q`.
EOF
cat > README.md <<'EOF'
# orders

Takes an order as a dict, checks its shape and stores it.

Dependencies are pinned in `requirements.txt`.

The order's shape is described in `schema/order.schema.json`.
EOF
cat > requirements.txt <<'EOF'
# Pinned third-party packages go here, one per line.
EOF
cat > schema/order.schema.json <<'EOF'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://shop.example/schemas/order.schema.json",
  "title": "Order",
  "type": "object",
  "required": ["id", "customer", "lines"],
  "additionalProperties": false,
  "properties": {
    "id": {"type": "string", "pattern": "^ORD-[0-9]{6}$"},
    "customer": {
      "oneOf": [
        {"$ref": "#/$defs/person"},
        {"$ref": "#/$defs/company"}
      ]
    },
    "placed_at": {"type": "string", "format": "date-time"},
    "lines": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/line"}}
  },
  "$defs": {
    "person": {
      "type": "object",
      "required": ["name", "email"],
      "additionalProperties": false,
      "properties": {
        "name": {"type": "string", "minLength": 1},
        "email": {"type": "string", "format": "email"}
      }
    },
    "company": {
      "type": "object",
      "required": ["company", "vat_id"],
      "additionalProperties": false,
      "properties": {
        "company": {"type": "string", "minLength": 1},
        "vat_id": {"type": "string", "pattern": "^[A-Z]{2}[0-9A-Z]{8,12}$"}
      }
    },
    "line": {
      "type": "object",
      "required": ["sku", "quantity"],
      "additionalProperties": false,
      "properties": {
        "sku": {"type": "string", "pattern": "^[A-Z0-9-]{4,16}$"},
        "quantity": {"type": "integer", "minimum": 1}
      }
    }
  }
}
EOF
cat > orders/__init__.py <<'EOF'
from orders.intake import accept_order

__all__ = ["accept_order"]
EOF
cat > orders/intake.py <<'EOF'
"""Takes an incoming order and stores it."""

STORE = []


def accept_order(order):
    """Store the order and return its id. An order is a dict."""
    STORE.append(order)
    return order["id"]
EOF
cat > tests/test_intake.py <<'EOF'
import unittest

from orders import intake


class AcceptOrderTest(unittest.TestCase):
    def setUp(self):
        intake.STORE.clear()

    def test_a_stored_order_is_returned_by_id(self):
        order = {"id": "ORD-000001", "customer": {"name": "Ada", "email": "ada@example.com"},
                 "lines": [{"sku": "TEA-100", "quantity": 2}]}
        self.assertEqual(intake.accept_order(order), "ORD-000001")
        self.assertEqual(intake.STORE, [order])

    def test_orders_are_kept_in_the_order_they_came(self):
        for n in (1, 2, 3):
            intake.accept_order({"id": "ORD-00000%d" % n})
        self.assertEqual([o["id"] for o in intake.STORE], ["ORD-000001", "ORD-000002", "ORD-000003"])


if __name__ == "__main__":
    unittest.main()
EOF
