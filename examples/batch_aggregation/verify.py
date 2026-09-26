"""Protected development checks; standard-library only."""

import copy
import json
import random

from processor import aggregate_orders


def reference(orders, customers):
    accepted = []
    for order in orders:
        matches = [customer for customer in customers if customer["id"] == order["customer_id"]]
        if order["status"] == "paid" and matches and matches[0]["active"]:
            accepted.append((matches[0]["region"], order["amount_cents"]))
    return [
        {
            "region": region,
            "order_count": sum(item[0] == region for item in accepted),
            "total_cents": sum(amount for key, amount in accepted if key == region),
        }
        for region in sorted({item[0] for item in accepted})
    ]


def check(orders, customers):
    before = copy.deepcopy((orders, customers))
    actual = aggregate_orders(orders, customers)
    assert actual == reference(*before), (actual, reference(*before))
    assert (orders, customers) == before, "Inputs must not be mutated"
    assert aggregate_orders(orders, customers) == actual, "Repeated calls must agree"


def main():
    check([], [])
    check(
        [
            {"customer_id": 1, "status": "paid", "amount_cents": 100},
            {"customer_id": 2, "status": "paid", "amount_cents": -35},
            {"customer_id": 2, "status": "pending", "amount_cents": 999},
            {"customer_id": 99, "status": "paid", "amount_cents": 500},
        ],
        [
            {"id": 1, "region": "Tokyo", "active": False},
            {"id": 1, "region": "Taipei", "active": True},
            {"id": 2, "region": "Taipei", "active": True},
        ],
    )
    for seed in range(24):
        rng = random.Random(seed)
        ids = list(range(16)) + ["16", "customer", None]
        customers = [
            {"id": rng.choice(ids), "region": rng.choice(["Tokyo", "台北", "", "Osaka"]),
             "active": rng.choice([True, False])}
            for _ in range(rng.randrange(45))
        ]
        orders = [
            {"customer_id": rng.choice(ids + ["unknown", -1]),
             "status": rng.choice(["paid", "pending", "cancelled"]),
             "amount_cents": rng.randrange(-10000, 10001)}
            for _ in range(rng.randrange(160))
        ]
        check(orders, customers)
    print(json.dumps({"passed": True, "cases": 26}))


if __name__ == "__main__":
    main()
