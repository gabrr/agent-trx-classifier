from datetime import date as Date
from datetime import datetime
from enum import StrEnum
from math import isclose, isfinite

from pydantic import BaseModel, Field, field_validator, model_validator


class StatementKind(StrEnum):
    CREDIT_CARD = "credit_card"
    CHECKING_ACCOUNT = "checking_account"
    UNKNOWN = "unknown"


class ReportBucket(StrEnum):
    INSTALLMENTS = "installments"
    FIXED = "fixed"
    VARIABLE = "variable"
    MOVEMENTS = "movements"


class StatementMetadata(BaseModel):
    kind: StatementKind
    institution_name: str | None = None
    currency: str | None = None
    statement_due_date: Date | None = None
    statement_close_date: Date | None = None
    statement_total: str | None = None
    page_count: int | None = None

    @field_validator("statement_total", mode="before")
    @classmethod
    def _statement_total_as_string(cls, value: object) -> str | None:
        return _decimal_as_string(value)

    @field_validator("statement_due_date", "statement_close_date", mode="before")
    @classmethod
    def _dates_as_iso(cls, value: object) -> Date | None:
        return _date_value(value)


class ExtractedTransaction(BaseModel):
    date: Date | None = None
    description: str | None = None
    amount: str | None = None
    currency: str | None = None
    cardholder: str | None = None
    card_last4: str | None = None
    payment_method: str | None = None
    merchant_name: str | None = None
    installments_current: int | None = None
    installments: int | None = None
    foreign_amount: str | None = None
    foreign_currency: str | None = None
    running_balance: str | None = None

    @field_validator("amount", "foreign_amount", "running_balance", mode="before")
    @classmethod
    def _amounts_as_strings(cls, value: object) -> str | None:
        return _decimal_as_string(value)

    @field_validator("date", mode="before")
    @classmethod
    def _date_as_iso(cls, value: object) -> Date | None:
        return _date_value(value)


class ExtractedStatement(BaseModel):
    statement: StatementMetadata
    transactions: list[ExtractedTransaction] = Field(strict=True)


class NormalizedTransaction(ExtractedTransaction):
    id: str
    report_bucket: ReportBucket
    classification_confidence: float = Field(ge=0, le=1)

    classification_probabilities: dict[ReportBucket, float]

    @model_validator(mode="after")
    def _valid_probabilities(self):
        values = self.classification_probabilities

        if set(values) != set(ReportBucket):
            raise ValueError("Probabilities must include every report bucket.")

        if any(not isfinite(value) or not 0 <= value <= 1 for value in values.values()):
            raise ValueError("Probabilities must be finite numbers between 0 and 1.")

        if not isclose(sum(values.values()), 1, abs_tol=0.02):
            raise ValueError("Probabilities must sum to one.")

        return self


class RunMetrics(BaseModel):
    elapsed_seconds: float = 0
    classification_seconds: float = 0
    classification_model_calls: int = 0
    transaction_count: int = 0


class NormalizedStatement(BaseModel):
    statement: StatementMetadata
    transactions: list[NormalizedTransaction] = Field(default_factory=list)

    metrics: RunMetrics = Field(default_factory=RunMetrics)


def _decimal_as_string(value: object) -> str | None:
    if value is None:
        return None

    return str(value)


def _date_value(value: object) -> Date | None:
    if value is None or isinstance(value, Date):
        return value

    if not isinstance(value, str):
        raise ValueError("date must be a string or date")

    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue

    raise ValueError(f"unsupported date format: {value!r}")
