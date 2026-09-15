"""
FinTech Growth & Revenue Funnel — Synthetic Data Generator

Connects to the local PostgreSQL instance and populates:
  - users                  (>= 1,000 rows, last 6 months)
  - user_events            (onboarding funnel with realistic drop-off)
  - financial_transactions (deposits for users who reach monetization)

Funnel drop-off targets (business rule):
  account_created          100%
  document_uploaded         ~70%
  kyc_approved              ~40%   (verification failure is the main bottleneck)
  first_deposit_initiated   ~25%

Usage:
  1. docker compose up -d
  2. pip install -r requirements.txt
  3. python scripts/generate_data.py
"""

from __future__ import annotations

import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg2
from faker import Faker
from psycopg2.extras import execute_batch

# ---------------------------------------------------------------------------
# Configuration (override via environment variables if needed)
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "fintech_growth"),
    "user": os.getenv("DB_USER", "admin"),
    "password": os.getenv("DB_PASSWORD", "password123"),
}

NUM_USERS = int(os.getenv("NUM_USERS", "1200"))
LOOKBACK_DAYS = 180  # last ~6 months
BATCH_SIZE = 500
RANDOM_SEED = 42

# Funnel conversion rates (applied sequentially from the full cohort)
FUNNEL_RATES = {
    "account_created": 1.00,
    "document_uploaded": 0.70,
    "kyc_approved": 0.40,
    "first_deposit_initiated": 0.25,
}

ACQUISITION_CHANNELS = [
    ("organic_search", 0.28),
    ("paid_social", 0.22),
    ("referral", 0.18),
    ("affiliate", 0.12),
    ("app_store", 0.12),
    ("email_campaign", 0.08),
]

USER_SEGMENTS = [
    ("retail", 0.45),
    ("mass_affluent", 0.20),
    ("student", 0.15),
    ("freelancer", 0.12),
    ("small_business", 0.08),
]

DEVICE_TYPES = [
    ("mobile_ios", 0.38),
    ("mobile_android", 0.42),
    ("desktop_web", 0.15),
    ("tablet", 0.05),
]

TRANSACTION_TYPES = [
    ("deposit", 0.75),
    ("fee", 0.10),
    ("transfer", 0.10),
    ("withdrawal", 0.05),
]

fake = Faker()
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)


def weighted_choice(options: list[tuple[str, float]]) -> str:
    """Return one label from a list of (label, weight) pairs."""
    labels, weights = zip(*options)
    return random.choices(labels, weights=weights, k=1)[0]


def random_signup_timestamp(now: datetime) -> datetime:
    """Uniform random signup within the lookback window."""
    offset_seconds = random.randint(0, LOOKBACK_DAYS * 24 * 3600)
    ts = now - timedelta(seconds=offset_seconds)
    # Prefer weekday daytime signups for realism
    if ts.weekday() >= 5:
        ts -= timedelta(days=random.randint(1, 2))
    hour = int(random.gauss(14, 4))
    hour = max(7, min(22, hour))
    return ts.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59), microsecond=0)


def add_funnel_delay(base: datetime, stage: str) -> datetime:
    """
    Add a realistic time gap between consecutive funnel stages.
    KYC tends to take longer (manual / async verification).
    """
    delays = {
        "document_uploaded": (timedelta(minutes=5), timedelta(hours=48)),
        "kyc_approved": (timedelta(hours=2), timedelta(days=5)),
        "first_deposit_initiated": (timedelta(minutes=10), timedelta(days=14)),
    }
    low, high = delays[stage]
    delta_seconds = random.randint(int(low.total_seconds()), int(high.total_seconds()))
    return base + timedelta(seconds=delta_seconds)


def build_users(n: int, now: datetime) -> list[dict[str, Any]]:
    """Generate user dimension rows."""
    users = []
    for _ in range(n):
        users.append(
            {
                "user_id": str(uuid.uuid4()),
                "signup_timestamp": random_signup_timestamp(now),
                "acquisition_channel": weighted_choice(ACQUISITION_CHANNELS),
                "user_segment": weighted_choice(USER_SEGMENTS),
            }
        )
    return users


def build_funnel_events(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Emit onboarding events with cohort-level drop-off matching FUNNEL_RATES.

    Approach: shuffle the cohort once, then assign progressive stage reach
    based on cumulative conversion targets so rates stay stable at scale.
    """
    n = len(users)
    # How many users should reach each stage (from full cohort)
    n_docs = int(round(n * FUNNEL_RATES["document_uploaded"]))
    n_kyc = int(round(n * FUNNEL_RATES["kyc_approved"]))
    n_deposit = int(round(n * FUNNEL_RATES["first_deposit_initiated"]))

    # Ensure monotonic funnel: deposit ⊆ kyc ⊆ docs ⊆ all
    n_kyc = min(n_kyc, n_docs)
    n_deposit = min(n_deposit, n_kyc)

    shuffled = users.copy()
    random.shuffle(shuffled)

    reach_docs = {u["user_id"] for u in shuffled[:n_docs]}
    reach_kyc = {u["user_id"] for u in shuffled[:n_kyc]}
    reach_deposit = {u["user_id"] for u in shuffled[:n_deposit]}

    events: list[dict[str, Any]] = []

    for user in users:
        uid = user["user_id"]
        device = weighted_choice(DEVICE_TYPES)
        ts = user["signup_timestamp"]

        # Stage 1 — every user creates an account at signup
        events.append(
            {
                "event_id": str(uuid.uuid4()),
                "user_id": uid,
                "event_name": "account_created",
                "event_timestamp": ts,
                "device_type": device,
            }
        )

        if uid not in reach_docs:
            continue

        ts = add_funnel_delay(ts, "document_uploaded")
        events.append(
            {
                "event_id": str(uuid.uuid4()),
                "user_id": uid,
                "event_name": "document_uploaded",
                "event_timestamp": ts,
                "device_type": device,
            }
        )

        if uid not in reach_kyc:
            continue

        ts = add_funnel_delay(ts, "kyc_approved")
        events.append(
            {
                "event_id": str(uuid.uuid4()),
                "user_id": uid,
                "event_name": "kyc_approved",
                "event_timestamp": ts,
                "device_type": device,
            }
        )

        if uid not in reach_deposit:
            continue

        ts = add_funnel_delay(ts, "first_deposit_initiated")
        events.append(
            {
                "event_id": str(uuid.uuid4()),
                "user_id": uid,
                "event_name": "first_deposit_initiated",
                "event_timestamp": ts,
                "device_type": device,
            }
        )

    return events


def build_transactions(
    users: list[dict[str, Any]],
    events: list[dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """
    Create financial transactions for users who initiated a first deposit.
    Includes a realistic mix of completed vs failed payments.
    """
    deposit_by_user = {
        e["user_id"]: e["event_timestamp"]
        for e in events
        if e["event_name"] == "first_deposit_initiated"
    }
    segment_by_user = {u["user_id"]: u["user_segment"] for u in users}

    # Typical first-deposit size by segment (min, max)
    amount_ranges = {
        "retail": (20, 250),
        "mass_affluent": (200, 2500),
        "student": (10, 100),
        "freelancer": (50, 800),
        "small_business": (100, 5000),
    }

    transactions: list[dict[str, Any]] = []

    for uid, first_ts in deposit_by_user.items():
        segment = segment_by_user[uid]
        lo, hi = amount_ranges.get(segment, (20, 500))

        # First deposit attempt (mostly successful; ~12% fail on payment rail)
        first_status = "failed" if random.random() < 0.12 else "completed"
        transactions.append(
            {
                "transaction_id": str(uuid.uuid4()),
                "user_id": uid,
                "transaction_type": "deposit",
                "amount": Decimal(str(round(random.uniform(lo, hi), 2))),
                "status": first_status,
                "created_at": first_ts,
            }
        )

        # Optional follow-up activity for engaged users
        if first_status == "completed" and random.random() < 0.55:
            extra = random.randint(1, 4)
            cursor = first_ts
            for _ in range(extra):
                cursor = cursor + timedelta(days=random.randint(1, 21))
                if cursor > now:
                    break
                tx_type = weighted_choice(TRANSACTION_TYPES)
                status = "failed" if random.random() < 0.08 else "completed"
                transactions.append(
                    {
                        "transaction_id": str(uuid.uuid4()),
                        "user_id": uid,
                        "transaction_type": tx_type,
                        "amount": Decimal(str(round(random.uniform(lo * 0.5, hi * 1.2), 2))),
                        "status": status,
                        "created_at": cursor,
                    }
                )

    return transactions


def connect():
    """Open a PostgreSQL connection using DB_CONFIG."""
    return psycopg2.connect(**DB_CONFIG)


def truncate_tables(conn) -> None:
    """Clear existing synthetic data before reloading (idempotent runs)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE TABLE
                financial_transactions,
                user_events,
                users
            RESTART IDENTITY CASCADE
            """
        )
    conn.commit()


def insert_users(conn, users: list[dict[str, Any]]) -> None:
    sql = """
        INSERT INTO users (user_id, signup_timestamp, acquisition_channel, user_segment)
        VALUES (%(user_id)s, %(signup_timestamp)s, %(acquisition_channel)s, %(user_segment)s)
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, users, page_size=BATCH_SIZE)
    conn.commit()


def insert_events(conn, events: list[dict[str, Any]]) -> None:
    sql = """
        INSERT INTO user_events (event_id, user_id, event_name, event_timestamp, device_type)
        VALUES (%(event_id)s, %(user_id)s, %(event_name)s, %(event_timestamp)s, %(device_type)s)
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, events, page_size=BATCH_SIZE)
    conn.commit()


def insert_transactions(conn, transactions: list[dict[str, Any]]) -> None:
    sql = """
        INSERT INTO financial_transactions
            (transaction_id, user_id, transaction_type, amount, status, created_at)
        VALUES
            (%(transaction_id)s, %(user_id)s, %(transaction_type)s,
             %(amount)s, %(status)s, %(created_at)s)
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, transactions, page_size=BATCH_SIZE)
    conn.commit()


def print_funnel_summary(events: list[dict[str, Any]], n_users: int) -> None:
    """Print realized conversion rates vs target for quick QA."""
    counts: dict[str, int] = {}
    for e in events:
        counts[e["event_name"]] = counts.get(e["event_name"], 0) + 1

    print("\n=== Funnel Summary ===")
    print(f"{'Stage':<28} {'Users':>8} {'Rate':>8} {'Target':>8}")
    for stage, target in FUNNEL_RATES.items():
        c = counts.get(stage, 0)
        rate = c / n_users if n_users else 0
        print(f"{stage:<28} {c:>8} {rate:>7.1%} {target:>7.0%}")


def main() -> None:
    now = datetime.now(timezone.utc)
    print(f"Generating synthetic data for {NUM_USERS} users (lookback={LOOKBACK_DAYS} days)...")

    users = build_users(NUM_USERS, now)
    events = build_funnel_events(users)
    transactions = build_transactions(users, events, now)

    print(f"  users:                 {len(users):,}")
    print(f"  user_events:           {len(events):,}")
    print(f"  financial_transactions:{len(transactions):,}")

    print(f"\nConnecting to PostgreSQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}...")
    conn = connect()
    try:
        print("Truncating previous data...")
        truncate_tables(conn)

        print("Inserting users...")
        insert_users(conn, users)

        print("Inserting user_events...")
        insert_events(conn, events)

        print("Inserting financial_transactions...")
        insert_transactions(conn, transactions)

        print_funnel_summary(events, len(users))
        print("\nDone. Database is ready for funnel analysis.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
