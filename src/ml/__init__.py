"""Shared deterministic dataset splitting for baselines and future models."""

from __future__ import annotations

import hashlib
from enum import Enum


SPLIT_VERSION = "sha256-transaction-id-mod-100-v1"


class DatasetSplit(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


def split_for_transaction(transaction_id: str) -> DatasetSplit:
    """Assign a stable 70/15/15 split without using scenario labels."""
    bucket = int.from_bytes(hashlib.sha256(transaction_id.encode("utf-8")).digest()[:8]) % 100
    if bucket < 70:
        return DatasetSplit.TRAIN
    if bucket < 85:
        return DatasetSplit.VALIDATION
    return DatasetSplit.TEST
