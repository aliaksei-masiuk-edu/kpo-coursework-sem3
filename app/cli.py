import argparse
from datetime import timedelta
from getpass import getpass

from sqlalchemy import func, select

from app.database import Base, build_database
from app.models import RepairOrder, User
from app.schemas import UserInput
from app.security import password_hasher
from app.services import today


def main():
    parser = argparse.ArgumentParser(description="Подготовка базы сервисного центра")
    parser.add_argument("command", choices=["init-demo", "create-admin"])
    args = parser.parse_args()
    engine, factory = build_database()
    Base.metadata.create_all(engine)
    with factory() as db:
        if args.command == "create-admin":
            data = UserInput(
                username=input("Логин: "),
                full_name=input("Имя: "),
                password=getpass("Пароль (минимум 10 символов): "),
                role="admin",
            )
            if db.scalar(select(User).where(User.username == data.username.lower())):
                parser.error("Этот логин уже занят")
            db.add(
                User(
                    username=data.username.lower(),
                    full_name=data.full_name,
                    role="admin",
                    password_hash=password_hasher.hash(data.password),
                )
            )
            db.commit()
            print("Администратор создан.")
        else:
            for login, name, role, password in [
                ("admin", "Администратор сервиса", "admin", "AdminDemo2026!"),
                ("operator", "Оператор сервиса", "operator", "OperatorDemo2026!"),
            ]:
                if not db.scalar(select(User).where(User.username == login)):
                    db.add(
                        User(
                            username=login,
                            full_name=name,
                            role=role,
                            password_hash=password_hasher.hash(password),
                        )
                    )
            db.flush()
            admin = db.scalar(select(User).where(User.username == "admin"))
            if not db.scalar(select(func.count(RepairOrder.id))):
                samples = [
                    ("Телевизор", "Samsung UE50", "Иванов Иван Иванович", "120.00", -10, -3, None),
                    ("Ноутбук", "Lenovo IdeaPad", "Петрова Анна Сергеевна", "185.50", -8, -1, None),
                    (
                        "Кофемашина",
                        "DeLonghi Magnifica",
                        "Сидоров Павел Олегович",
                        "95.00",
                        -5,
                        0,
                        None,
                    ),
                    (
                        "Смартфон",
                        "Apple iPhone 13",
                        "Козлова Мария Игоревна",
                        "210.00",
                        -3,
                        2,
                        None,
                    ),
                    ("Пылесос", "Dyson V10", "Мороз Дмитрий Андреевич", "75.30", -2, 5, None),
                    ("Монитор", "LG UltraWide", "Волкова Елена Петровна", "90.10", -12, -4, -2),
                    ("Планшет", "Samsung Galaxy Tab", "Орлов Максим Юрьевич", "145.20", -7, -1, -1),
                ]
                for i, (item, brand, owner, cost, received, planned, completed) in enumerate(
                    samples
                ):
                    from decimal import Decimal

                    db.add(
                        RepairOrder(
                            item_name=item,
                            brand=brand,
                            owner_name=owner,
                            owner_phone=f"+375 29 555-01-{i:02d}",
                            cost_cents=int(Decimal(cost) * 100),
                            received_on=today() + timedelta(days=received),
                            planned_on=today() + timedelta(days=planned),
                            completed_on=today() + timedelta(days=completed) if completed else None,
                            created_by=admin.id,
                        )
                    )
            db.commit()
            print("Демонстрационная база готова. Существующие записи и пароли не изменены.")
            print("Для новых аккаунтов: admin / AdminDemo2026!; operator / OperatorDemo2026!")
    engine.dispose()


if __name__ == "__main__":
    main()
