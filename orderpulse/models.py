from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="nonnegative_amount"),
        CheckConstraint(
            "status IN ('paid', 'pending', 'cancelled', 'refunded')", name="known_status"
        ),
        Index("ix_orders_status_created_at", "status", "created_at"),
    )

    order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime]
    country: Mapped[str] = mapped_column(String(2))
    amount_cents: Mapped[int]
    status: Mapped[str] = mapped_column(String(9))
