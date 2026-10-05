from decimal import Decimal, InvalidOperation

from .transaction_evaluators import (
    amount_accuracy,
    end_to_end_bucket_accuracy,
    report_bucket_accuracy,
    transaction_count,
    transaction_match_rate,
)


def money(value: object) -> Decimal:
    amount = Decimal(str(value))

    if not amount.is_finite():
        raise ValueError("Amounts must be finite decimals.")

    return amount.quantize(Decimal("0.01"))


def statement_total_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    try:
        actual = money(outputs["statement"]["statement_total"])

        expected = money(reference_outputs["statement"]["statement_total"])

    except (InvalidOperation, KeyError, ValueError, TypeError):
        return {"key": "statement_total_accuracy", "score": False}

    return {"key": "statement_total_accuracy", "score": actual == expected}


def signed_transaction_total_accuracy(outputs: dict, reference_outputs: dict) -> dict:
    try:
        actual = sum(
            (money(row["amount"]) for row in outputs["transactions"]), Decimal(0)
        )

        expected = sum(
            (money(row["amount"]) for row in reference_outputs["transactions"]),
            Decimal(0),
        )

    except (InvalidOperation, KeyError, ValueError, TypeError):
        return {"key": "signed_transaction_total_accuracy", "score": False}

    return {
        "key": "signed_transaction_total_accuracy",
        "score": actual == expected,
        "comment": f"Actual: {actual}; expected: {expected}",
    }


def workflow_duration(outputs: dict) -> dict:
    return {"key": "workflow_seconds", "score": outputs["metrics"]["elapsed_seconds"]}


EVALUATORS = [
    transaction_count,
    transaction_match_rate,
    amount_accuracy,
    report_bucket_accuracy,
    end_to_end_bucket_accuracy,
    statement_total_accuracy,
    signed_transaction_total_accuracy,
    workflow_duration,
]
