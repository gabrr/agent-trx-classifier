from sqlalchemy import select

from db.models import Account


def create_account(
    session, owner_id, *, name, type, currency, opening_balance=0, institution_name=None
):
    account = Account(
        owner_id=owner_id,
        name=name,
        type=type,
        currency=currency,
        opening_balance=opening_balance,
        institution_name=institution_name,
        is_active=True,
    )

    session.add(account)

    session.flush()

    return account


def get_account(session, owner_id, account_id):
    account = session.scalar(
        select(Account).where(Account.id == account_id, Account.owner_id == owner_id)
    )

    if account is None:
        raise LookupError("Account not found")

    return account
