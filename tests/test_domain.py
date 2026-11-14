import unittest
from marketcontrol.catalog import Catalog
from marketcontrol.domain import registered_turnover


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog("data")

    def test_registered_turnover_preserves_total(self):
        total = sum(float(value) for value in registered_turnover(self.catalog).values())
        self.assertAlmostEqual(total, sum(float(record["amount"]) for record in self.catalog.rows("transactions")))
        self.assertTrue(any(record["right_kind"] == "joint" for record in self.catalog.rows("ownership")))


    def test_turnover_is_decimal_and_identity_based(self):
        records = [{"entity_id": "A", "amount": "0.10"}, {"entity_id": "A", "amount": "0.20"}]
        self.assertEqual(registered_turnover(FakeCatalog({"transactions": records}))["A"], "0.30")

    def test_empty_registry(self):
        self.assertEqual(registered_turnover(FakeCatalog({"transactions": []})), {})

    def test_transaction_order_does_not_change_totals(self):
        records = self.catalog.rows("transactions")
        self.assertEqual(registered_turnover(FakeCatalog({"transactions": list(reversed(records))})), registered_turnover(self.catalog))

    def test_distinct_legal_entities_remain_distinct_in_registry(self):
        records = [{"entity_id": name, "amount": "1.00"} for name in ("A", "B")]
        self.assertEqual(len(registered_turnover(FakeCatalog({"transactions": records}))), 2)


class FakeCatalog:
    def __init__(self, tables):
        self.tables = tables

    def rows(self, name):
        return self.tables[name]
