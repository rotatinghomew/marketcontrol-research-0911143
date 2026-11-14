from collections import defaultdict
from decimal import Decimal


def registered_turnover(catalog):
    totals = defaultdict(Decimal)
    for record in catalog.rows("transactions"):
        totals[record["entity_id"]] += Decimal(record["amount"])
    return {entity: str(amount) for entity, amount in sorted(totals.items())}


def overview(catalog):
    return {"登记经营主体成交": registered_turnover(catalog), "关系证据数": len(catalog.rows("ownership")), "覆盖声明": catalog.rows("coverage")}
