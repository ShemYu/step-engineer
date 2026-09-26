"""Protected workload. The external runner measures process elapsed time."""

import json

from processor import aggregate_orders


def main():
    customer_count = 6000
    order_count = 18000
    customers = [
        {"id": i, "region": f"region-{i % 19:02d}", "active": i % 11 != 0}
        for i in range(customer_count)
    ]
    orders = [
        {"customer_id": (i * 37) % customer_count,
         "status": "pending" if i % 7 == 0 else "paid",
         "amount_cents": (i * 97) % 50000 - 1000}
        for i in range(order_count)
    ]
    result = aggregate_orders(orders, customers)
    count = sum(row["order_count"] for row in result)
    total = sum(row["total_cents"] for row in result)
    accepted = [i for i in range(order_count) if i % 7 != 0 and ((i * 37) % customer_count) % 11]
    assert count == len(accepted)
    assert total == sum((i * 97) % 50000 - 1000 for i in accepted)
    assert [row["region"] for row in result] == sorted(row["region"] for row in result)
    # No elapsed_seconds field: the candidate cannot self-report the timing metric.
    print(json.dumps({"customers": customer_count, "orders": order_count,
                      "accepted_orders": count, "total_cents": total}))


if __name__ == "__main__":
    main()
