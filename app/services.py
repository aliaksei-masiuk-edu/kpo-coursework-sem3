from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select

from app.models import RepairOrder


def today():
    return datetime.now(ZoneInfo("Europe/Minsk")).date()


def money(cents: int):
    return f"{Decimal(cents) / 100:.2f}"


def order_dict(order):
    return {
        "id": order.id,
        "item_name": order.item_name,
        "brand": order.brand,
        "owner_name": order.owner_name,
        "owner_phone": order.owner_phone,
        "cost": money(order.cost_cents),
        "received_on": order.received_on,
        "planned_on": order.planned_on,
        "completed_on": order.completed_on,
        "is_completed": order.completed_on is not None,
        "is_overdue": order.completed_on is None and order.planned_on < today(),
    }


def get_order(db, order_id):
    order = db.get(RepairOrder, order_id)
    if order is None:
        raise HTTPException(404, "Заказ не найден")
    return order


def set_order_fields(order, data):
    if data.received_on > today():
        raise HTTPException(422, "Дата приёмки не может быть в будущем")
    if order.completed_on and data.received_on > order.completed_on:
        raise HTTPException(422, "Дата приёмки не может быть позже выполнения")
    for key, value in data.model_dump(exclude={"cost"}).items():
        setattr(order, key, value)
    order.cost_cents = int(data.cost * 100)


def list_orders(db, status="all", search="", offset=0, limit=100):
    stmt = select(RepairOrder)
    if status in {"pending", "overdue"}:
        stmt = stmt.where(RepairOrder.completed_on.is_(None))
    if status == "overdue":
        stmt = stmt.where(RepairOrder.planned_on < today())
    elif status == "completed":
        stmt = stmt.where(RepairOrder.completed_on.is_not(None))
    if search.strip():
        term = search.strip()
        if term.startswith("#") and term[1:].isascii() and term[1:].isdigit():
            number = int(term[1:])
            stmt = stmt.where(RepairOrder.id == (number if number <= 2**63 - 1 else -1))
        else:
            stmt = stmt.where(
                or_(
                    *[
                        func.lower(field).contains(term.casefold(), autoescape=True)
                        for field in (
                            RepairOrder.item_name,
                            RepairOrder.brand,
                            RepairOrder.owner_name,
                            RepairOrder.owner_phone,
                        )
                    ]
                )
            )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    # Сначала просроченные, затем остальные невыполненные; внутри групп — по плановой дате.
    stmt = (
        stmt.order_by(
            case(
                (RepairOrder.completed_on.is_not(None), 2),
                (RepairOrder.planned_on < today(), 0),
                else_=1,
            ),
            RepairOrder.planned_on,
            RepairOrder.id,
        )
        .offset(offset)
        .limit(limit)
    )
    return {"items": [order_dict(o) for o in db.scalars(stmt)], "total": total}


def revenue_report(db, start: date, end: date):
    if start > end:
        raise HTTPException(422, "Начальная дата должна быть не позже конечной")
    orders = db.scalars(
        select(RepairOrder)
        .where(
            RepairOrder.completed_on.between(start, end),
        )
        .order_by(RepairOrder.completed_on, RepairOrder.id)
    ).all()
    return {
        "start": start,
        "end": end,
        "count": len(orders),
        "total": money(sum(order.cost_cents for order in orders)),
        "items": [order_dict(order) for order in orders],
    }
