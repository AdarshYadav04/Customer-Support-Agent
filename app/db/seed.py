"""Create tables and load demo data:  python -m app.db.seed"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Base, Customer, Order, OrderItem, OrderStatus, Product
from app.db.session import create_engine, create_session_factory


async def seed(session: AsyncSession) -> bool:
    """Insert demo data into an empty database. Returns False if data already exists."""
    count = (await session.execute(select(func.count()).select_from(Customer))).scalar_one()
    if count:
        return False

    now = datetime.now(timezone.utc)

    alex = Customer(email="alex@example.com", name="Alex Johnson")
    sam = Customer(email="sam@example.com", name="Sam Lee")
    earbuds = Product(
        sku="AUD-1001", name="Wireless Earbuds Pro", price=Decimal("79.99"), stock=25,
        description="Bluetooth 5.3 earbuds with noise cancelling and 30h battery.",
    )
    keyboard = Product(
        sku="KEY-2001", name="Mechanical Keyboard", price=Decimal("109.00"), stock=0,
        description="Hot-swappable mechanical keyboard with RGB backlight.",
    )
    shoes = Product(
        sku="SHO-3001", name="Trail Running Shoes", price=Decimal("129.50"), stock=12,
        description="Lightweight trail running shoes with a grippy sole.",
    )
    mat = Product(
        sku="FIT-4001", name="Yoga Mat", price=Decimal("29.00"), stock=40,
        description="6mm non-slip yoga mat for home workouts.",
    )
    session.add_all([alex, sam, earbuds, keyboard, shoes, mat])
    await session.flush()

    def order(number, customer, status, total, items, **kw) -> Order:
        o = Order(order_number=number, customer_id=customer.id, status=status, total=total, **kw)
        o.items = [
            OrderItem(product_id=p.id, quantity=q, unit_price=p.price) for p, q in items
        ]
        return o

    session.add_all([
        order(  # delivered recently -> returnable
            "ORD-1001", alex, OrderStatus.DELIVERED, Decimal("79.99"), [(earbuds, 1)],
            carrier="BlueDart", tracking_number="BD123456789",
            placed_at=now - timedelta(days=14), delivered_at=now - timedelta(days=10),
        ),
        order(  # in transit
            "ORD-1002", alex, OrderStatus.SHIPPED, Decimal("158.50"), [(shoes, 1), (mat, 1)],
            carrier="Delhivery", tracking_number="DL987654321",
            estimated_delivery=date.today() + timedelta(days=2),
            placed_at=now - timedelta(days=3),
        ),
        order(  # delivered long ago -> outside return window
            "ORD-1003", alex, OrderStatus.DELIVERED, Decimal("29.00"), [(mat, 1)],
            carrier="BlueDart", tracking_number="BD555000111",
            placed_at=now - timedelta(days=65), delivered_at=now - timedelta(days=60),
        ),
        order(  # another customer's order
            "ORD-2001", sam, OrderStatus.PROCESSING, Decimal("79.99"), [(earbuds, 1)],
            placed_at=now - timedelta(hours=5),
        ),
    ])
    await session.commit()
    return True


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with create_session_factory(engine)() as session:
        seeded = await seed(session)
    await engine.dispose()
    print("Seeded demo data (customers 1 and 2)." if seeded else "Data already present; nothing to do.")


if __name__ == "__main__":
    asyncio.run(main())
