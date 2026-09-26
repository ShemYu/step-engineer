"""Editable first-fit baseline: select feasible jobs in their input order."""


def select_jobs(jobs, cpu_budget, memory_budget):
    selected = []
    cpu_used = memory_used = 0
    for job in jobs:
        if cpu_used + job["cpu"] <= cpu_budget and memory_used + job["memory"] <= memory_budget:
            selected.append(job["id"])
            cpu_used += job["cpu"]
            memory_used += job["memory"]
    return selected
