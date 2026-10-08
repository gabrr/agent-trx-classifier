from sqlalchemy import or_, select

from db.models import Category


def list_categories(session, owner_id):
    return list(
        session.scalars(
            select(Category)
            .where(or_(Category.owner_id == owner_id, Category.is_system))
            .order_by(Category.name)
        )
    )


def get_category(session, owner_id, category_id):
    category = session.scalar(
        select(Category).where(
            Category.id == category_id,
            or_(Category.owner_id == owner_id, Category.is_system),
        )
    )

    if category is None:
        raise LookupError("Category not found")

    return category


def create_category(session, owner_id, *, key, name):
    category = Category(owner_id=owner_id, key=key, name=name, is_system=False)

    session.add(category)

    session.flush()

    return category
