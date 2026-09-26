"""Protected final-only checks with a separate oracle and broader cases.

This file is not imported by verify.py or bench.py. The job withholds it from the
optimizer's workspace and tools, then runs it in the final-validation workspace.
The source is included in this example for the parent engineer to review.
"""

import copy
import itertools
import json
import random

from processor import aggregate_orders


def final_oracle(orders, customers):
    first = {}
    for customer in reversed(customers):
        first[customer["id"]] = customer
    rows = []
    for order in orders:
        customer = first.get(order["customer_id"])
        if customer is not None and customer["active"] and order["status"] == "paid":
            rows.append((customer["region"], order["amount_cents"]))
    output = []
    for region, entries in itertools.groupby(sorted(rows), key=lambda item: item[0]):
        amounts = [amount for _, amount in entries]
        output.append({"region": region, "order_count": len(amounts), "total_cents": sum(amounts)})
    return output


def check(orders, customers):
    before = copy.deepcopy((orders, customers))
    expected = final_oracle(orders, customers)
    assert aggregate_orders(orders, customers) == expected
    assert (orders, customers) == before, "Inputs changed"
    # Permuting orders must not alter a grouped sum or order count.
    assert aggregate_orders(list(reversed(orders)), customers) == expected


def main():
    checked = 0
    for seed in (109, 271, 881, 1741, 8191, 65537):
        rng = random.Random(seed)
        ids = [*range(250), "0", "001", None, 10**30, -(10**30)]
        for size in (0, 1, 37, 513, 1400):
            customers = [
                {"id": rng.choice(ids), "region": rng.choice(["", "a", "A", "日本", "台灣", "é"]),
                 "active": rng.randrange(5) != 0, "unused": {"keep": [1, 2]}}
                for _ in range(size)
            ]
            orders = [
                {"customer_id": rng.choice(ids + ["missing"]),
                 "status": rng.choice(["paid", "paid", "pending", "cancelled"]),
                 "amount_cents": rng.choice([0, 1, -1, 2**70, -(2**70), rng.randrange(-5000, 5000)])}
                for _ in range(size * 2 + 3)
            ]
            check(orders, customers)
            checked += 1
    check(
        [{"customer_id": None, "status": "paid", "amount_cents": 2**80},
         {"customer_id": "0", "status": "paid", "amount_cents": -(2**80)},
         {"customer_id": 0, "status": "paid", "amount_cents": 5}],
        [{"id": None, "region": "same", "active": True},
         {"id": "0", "region": "same", "active": True},
         {"id": 0, "region": "same", "active": False},
         {"id": 0, "region": "wrong", "active": True}],
    )
    print(json.dumps({"passed": True, "final_cases": checked + 1}))


if __name__ == "__main__":
    main()
