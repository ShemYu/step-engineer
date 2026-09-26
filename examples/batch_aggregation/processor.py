"""Batch order aggregation: a deliberately slow, behaviorally correct baseline.

Contract: inputs are lists of dictionaries. Customer IDs are hashable (integer,
string, or None); regions are strings; amount_cents is an integer. The first
customer with a given ID wins, even if that customer is inactive. Only paid
orders for active, known customers contribute. Refunds may be negative. Return
one row per contributing region, sorted by region, without changing inputs.
"""


def aggregate_orders(orders: list[dict], customers: list[dict]) -> list[dict]:
    totals = {}
    for order in orders:
        if order["status"] != "paid":
            continue
        customer = None
        for candidate in customers:
            if candidate["id"] == order["customer_id"]:
                customer = candidate
                break
        if customer is None or not customer["active"]:
            continue
        region = customer["region"]
        if region not in totals:
            totals[region] = {"region": region, "order_count": 0, "total_cents": 0}
        totals[region]["order_count"] += 1
        totals[region]["total_cents"] += order["amount_cents"]
    return [totals[region] for region in sorted(totals)]
