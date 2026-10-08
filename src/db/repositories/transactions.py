from sqlalchemy import select

from db.models import ActivityEvent, Transaction
from workflows.trx_classifier.models import ExtractedTransaction, ReportBucket

from .categories import get_category

EDITABLE_FIELDS = set(ExtractedTransaction.model_fields) | {
    "category_id",
    "report_bucket_override",
}


def list_transactions(session, owner_id, statement_id):
    from db.models import Statement

    if (
        session.scalar(
            select(Statement.id).where(
                Statement.id == statement_id, Statement.owner_id == owner_id
            )
        )
        is None
    ):
        raise LookupError("Statement not found")

    return list(
        session.scalars(
            select(Transaction)
            .where(
                Transaction.owner_id == owner_id,
                Transaction.statement_id == statement_id,
            )
            .order_by(Transaction.position)
        )
    )


def edit_transaction(session, owner_id, transaction_id, changes):
    if set(changes) - EDITABLE_FIELDS:
        raise ValueError("Unsupported transaction field")

    transaction = session.scalar(
        select(Transaction)
        .where(Transaction.id == transaction_id, Transaction.owner_id == owner_id)
        .with_for_update()
    )

    if transaction is None:
        raise LookupError("Transaction not found")

    if changes.get("category_id") is not None:
        get_category(session, owner_id, changes["category_id"])

    if changes.get("report_bucket_override") is not None:
        ReportBucket(changes["report_bucket_override"])

    # Validate nullable extracted fields using TRX's existing rules.
    extracted = ExtractedTransaction.model_validate(
        {
            field: changes.get(field, getattr(transaction, field))
            for field in ExtractedTransaction.model_fields
        }
    )

    values = extracted.model_dump()

    json_values = extracted.model_dump(mode="json")

    for field, submitted in changes.items():
        old = getattr(transaction, field)

        new = values[field] if field in values else submitted
        if field == "report_bucket_override":
            old_effective = old or transaction.report_bucket
            new_effective = new or transaction.report_bucket
            audit_old, audit_new = old_effective, new_effective
        else:
            audit_old = (
                str(old)
                if field in {"date", "category_id"} and old is not None
                else old
            )

            audit_new = (
                json_values.get(field)
                if field in json_values
                else (str(new) if new is not None else None)
            )

        if old == new:
            continue

        setattr(transaction, field, new)

        if audit_old != audit_new:
            session.add(
                ActivityEvent(
                    changed_by=owner_id,
                    entity_id=transaction_id,
                    field=field,
                    old_value=audit_old,
                    new_value=audit_new,
                )
            )

    session.flush()

    return transaction


def activity_history(session, owner_id, transaction_id):
    if (
        session.scalar(
            select(Transaction.id).where(
                Transaction.id == transaction_id, Transaction.owner_id == owner_id
            )
        )
        is None
    ):
        raise LookupError("Transaction not found")

    return list(
        session.scalars(
            select(ActivityEvent)
            .where(
                ActivityEvent.entity_id == transaction_id,
                ActivityEvent.changed_by == owner_id,
            )
            .order_by(ActivityEvent.created_at)
        )
    )
