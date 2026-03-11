"""
utils/draw.py — Provably Fair drawing logic using Python's secrets module.

Algorithm:
  1. Collect all verified ticket entries (each ticket_no : holder_tg_id pair).
  2. Generate a cryptographically strong random seed (secrets.token_hex).
  3. Use the seed to deterministically pick a winner index.
  4. Record seed + entries count in draw_history table for public auditability.
"""

import secrets
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DrawResult:
    winner_tg_id: int
    winner_ticket: int
    winner_name: str
    draw_seed: str
    total_entries: int


def provably_fair_draw(entries: list) -> Optional[DrawResult]:
    """
    Perform a cryptographically fair draw.

    Args:
        entries: list of asyncpg.Record with fields:
                 ticket_no, holder_tg_id, full_name

    Returns:
        DrawResult with the winner info and audit seed, or None if no entries.
    """
    if not entries:
        logger.warning("Draw attempted with zero entries.")
        return None

    # Step 1: Generate a secure random seed
    seed_hex = secrets.token_hex(32)  # 256-bit random seed

    # Step 2: Use the seed to pick a deterministic index
    # SHA-256(seed) → integer → modulo len(entries) gives a fair index
    seed_int = int(hashlib.sha256(seed_hex.encode()).hexdigest(), 16)
    winner_index = seed_int % len(entries)

    winner = entries[winner_index]

    result = DrawResult(
        winner_tg_id=winner["holder_tg_id"],
        winner_ticket=winner["ticket_no"],
        winner_name=winner["full_name"],
        draw_seed=seed_hex,
        total_entries=len(entries),
    )

    logger.info(
        f"🎲 Draw complete | Winner ticket #{result.winner_ticket} "
        f"| Entries: {result.total_entries} | Seed: {seed_hex[:12]}..."
    )
    return result


def verify_draw(seed_hex: str, total_entries: int, claimed_index: int) -> bool:
    """
    Public verification function — allows anyone to verify a past draw.

    Args:
        seed_hex: The draw_seed stored in draw_history.
        total_entries: Total number of verified tickets in that lottery.
        claimed_index: The index of the claimed winner (ticket list is sorted by ticket_no).

    Returns:
        True if the draw result is mathematically provable.
    """
    seed_int = int(hashlib.sha256(seed_hex.encode()).hexdigest(), 16)
    expected_index = seed_int % total_entries
    return expected_index == claimed_index
