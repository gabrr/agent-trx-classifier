"""Explicit categories only; no_match is resolved locally to variable."""

CRITERIA = {
    "fixed": (
        "Recurring commitment: rent, subscription, membership, or a recurring "
        "base service fee. Not a one-off rental, purchase, usage-based charge, "
        "or prepaid credits. A service provider's name alone is insufficient."
    ),
    "movements": (
        "Transfer, refund, reversal, or credit-card bill payment. "
        "Not payment for a purchased product or service."
    ),
    "installments": (
        "Purchase or debt payment with explicit installment evidence: 'Parcela "
        "1/3', '3 de 12', or structured installment fields. A number of credits "
        "or units purchased is not installment evidence."
    ),
    "no_match": "No clear evidence for any of the three explicit categories.",
}
