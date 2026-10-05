from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from typing import Any


def transaction_count(outputs: dict, reference_outputs: dict) -> dict:
    actual = len(_transactions(outputs))

    expected = len(_transactions(reference_outputs))

    return {
        "key": "transaction_count",
        "score": actual == expected,
        "value": {"actual": actual, "expected": expected},
    }


def transaction_match_rate(outputs: dict, reference_outputs: dict) -> dict:
    expected_count = len(_transactions(reference_outputs))

    matched = len(_matched_pairs(outputs, reference_outputs))

    score = matched / expected_count if expected_count else 1.0

    return {
        "key": "transaction_match_rate",
        "score": score,
        "value": {"matched": matched, "expected": expected_count},
    }


def amount_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    pairs = _matched_pairs(outputs, reference_outputs)

    correct = sum(_amount(actual) == _amount(expected) for actual, expected in pairs)

    score = correct / len(pairs) if pairs else 0.0

    return {
        "key": "amount_accuracy",
        "score": score,
        "value": {"correct": correct, "matched": len(pairs)},
    }


def report_bucket_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    pairs = _matched_pairs_by_description(outputs, reference_outputs)

    correct = sum(
        actual.get("report_bucket") == expected.get("report_bucket")
        for actual, expected in pairs
    )

    score = correct / len(pairs) if pairs else 0.0

    return {
        "key": "report_bucket_accuracy",
        "score": score,
        "value": {"correct": correct, "matched": len(pairs)},
    }


def _matched_pairs_by_description(
    outputs: dict,
    reference_outputs: dict,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pair bucket predictions without coupling the score to extracted fields."""
    expected_by_description: dict[str, deque[dict[str, Any]]] = defaultdict(deque)

    for transaction in _transactions(reference_outputs):
        description = _normalize_description(transaction.get("description"))

        expected_by_description[description].append(transaction)

    pairs = []

    for transaction in _transactions(outputs):
        description = _normalize_description(transaction.get("description"))

        matches = expected_by_description.get(description)

        if matches:
            pairs.append((transaction, matches.popleft()))

    return pairs


def end_to_end_bucket_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    pairs = _matched_pairs(outputs, reference_outputs)

    expected_count = len(_transactions(reference_outputs))

    correct = sum(
        actual.get("report_bucket") == expected.get("report_bucket")
        for actual, expected in pairs
    )

    score = correct / expected_count if expected_count else 1.0

    return {
        "key": "end_to_end_bucket_accuracy",
        "score": score,
        "value": {"correct": correct, "expected": expected_count},
    }


def _transactions(payload: dict) -> list[dict[str, Any]]:
    transactions = payload.get("transactions", [])

    return transactions if isinstance(transactions, list) else []


def _matched_pairs(
    outputs: dict,
    reference_outputs: dict,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    expected_by_identity: dict[tuple, deque[dict[str, Any]]] = defaultdict(deque)

    for transaction in _transactions(reference_outputs):
        expected_by_identity[_identity(transaction)].append(transaction)

    pairs = []

    for transaction in _transactions(outputs):
        matches = expected_by_identity.get(_identity(transaction))

        if matches:
            pairs.append((transaction, matches.popleft()))

    return pairs


def _identity(transaction: dict[str, Any]) -> tuple:
    return (
        transaction.get("date"),
        _normalize_description(transaction.get("description")),
        transaction.get("currency"),
        transaction.get("installments_current"),
        transaction.get("installments"),
    )


def _normalize_description(value: object) -> str:
    return " ".join(str(value or "").upper().split())


def _amount(transaction: dict[str, Any]) -> Decimal | None:
    try:
        return Decimal(str(transaction.get("amount"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None
