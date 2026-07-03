"""Smoke test _compute_client_stats."""
import sys
sys.path.insert(0, "/app/backend")
from scan_router import _compute_client_stats

# Case A: 2 paid invoices, both on time, promises kept
inv_ontime = [
    {"status": "paid", "due_date": "2026-01-15", "paid_at": "2026-01-14T00:00:00Z",
     "promise_date": "2026-01-15", "amount": 500},
    {"status": "paid", "due_date": "2026-02-10", "paid_at": "2026-02-10T00:00:00Z",
     "promise_date": "2026-02-10", "amount": 800},
]
print("A on_time:", _compute_client_stats(inv_ontime))

# Case B: 3 paid invoices, all quite late, some promises broken
inv_late = [
    {"status": "paid", "due_date": "2026-01-01", "paid_at": "2026-01-25T00:00:00Z",
     "promise_date": "2026-01-10", "amount": 500},
    {"status": "paid", "due_date": "2026-02-01", "paid_at": "2026-02-20T00:00:00Z",
     "promise_date": None, "amount": 500},
    {"status": "promise_broken", "due_date": "2026-03-01", "promise_date": "2026-03-05", "amount": 800},
    {"status": "paid", "due_date": "2026-04-01", "paid_at": "2026-04-15T00:00:00Z",
     "promise_date": "2026-04-05", "amount": 200},
]
print("B risky :", _compute_client_stats(inv_late))

# Case C: only 1 paid invoice → None
inv_new = [{"status": "paid", "due_date": "2026-01-01", "paid_at": "2026-01-05T00:00:00Z", "amount": 100},
           {"status": "invoiced", "amount": 100}]
print("C <2 :", _compute_client_stats(inv_new))

# Case D: slow (5 days late, keep=100%)
inv_slow = [
    {"status": "paid", "due_date": "2026-01-01", "paid_at": "2026-01-06T00:00:00Z",
     "promise_date": "2026-01-06", "amount": 500},
    {"status": "paid", "due_date": "2026-02-01", "paid_at": "2026-02-06T00:00:00Z",
     "promise_date": "2026-02-06", "amount": 500},
]
print("D slow :", _compute_client_stats(inv_slow))
