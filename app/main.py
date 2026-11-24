import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.database import Base, build_database, get_db
from app.models import LoginSession, RepairOrder, User
from app.schemas import ActiveInput, CompletionInput, LoginInput, OrderInput, UserInput
from app.security import (
    COOKIE_NAME,
    DUMMY_HASH,
    admin_user,
    current_user,
    new_session,
    password_hasher,
    utcnow,
)
from app.services import (
    get_order,
    list_orders,
    money,
    order_dict,
    revenue_report,
    set_order_fields,
    today,
)

STATIC = Path(__file__).parent / "static"


def user_dict(user):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
    }


def create_app(database_url: str | None = None):
    engine, session_factory = build_database(database_url)

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        with session_factory() as db:
            db.execute(delete(LoginSession).where(LoginSession.expires_at <= utcnow()))
            db.commit()
        yield
        engine.dispose()

    app = FastAPI(title="Сервис · Учёт заказов", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if request.url.path == "/":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; "
                "base-uri 'self'; form-action 'self'"
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        labels = {
            "item_name": "Изделие",
            "brand": "Марка",
            "owner_name": "Ф. И. О.",
            "owner_phone": "Телефон",
            "cost": "Стоимость",
            "received_on": "Дата приёмки",
            "planned_on": "Плановая дата",
            "completed_on": "Дата выполнения",
            "username": "Логин",
            "password": "Пароль",
            "full_name": "Имя",
            "start": "Начало периода",
            "end": "Конец периода",
        }
        errors = []
        for error in exc.errors():
            field = str(error["loc"][-1])
            kind = error["type"]
            if kind == "value_error":
                message = str(error.get("ctx", {}).get("error", "Некорректное значение"))
            elif kind == "missing":
                message = "обязательное поле"
            elif kind.startswith("date"):
                message = "введите корректную дату в формате ГГГГ-ММ-ДД"
            elif kind == "decimal_max_places":
                message = "допустимо не более двух знаков после запятой"
            else:
                message = "некорректное значение или превышена допустимая длина"
            errors.append(f"{labels.get(field, field)}: {message}")
        return JSONResponse(status_code=422, content={"detail": "; ".join(errors)})

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def login(data: LoginInput, response: Response, db=Depends(get_db)):
        user = db.scalar(select(User).where(User.username == data.username.lower()))
        valid = password_hasher.verify(data.password, user.password_hash if user else DUMMY_HASH)
        if not user or not valid or not user.is_active:
            raise HTTPException(401, "Неверный логин или пароль")
        raw, session = new_session(db, user)
        response.set_cookie(
            COOKIE_NAME,
            raw,
            httponly=True,
            samesite="strict",
            max_age=8 * 60 * 60,
            secure=os.getenv("COOKIE_SECURE", "0") == "1",
            path="/",
        )
        return {"user": user_dict(user), "csrf_token": session.csrf_token, "today": today()}

    @app.get("/api/auth/me")
    def me(request: Request, user=Depends(current_user)):
        return {
            "user": user_dict(user),
            "csrf_token": request.state.login_session.csrf_token,
            "today": today(),
        }

    @app.post("/api/auth/logout", status_code=204)
    def logout(
        request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)
    ):
        db.delete(request.state.login_session)
        db.commit()
        response.delete_cookie(COOKIE_NAME, path="/")

    @app.get("/api/orders")
    def orders(
        status: Literal["all", "pending", "overdue", "completed"] = "all",
        search: str = Query("", max_length=150),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        return list_orders(db, status, search, offset, limit)

    @app.post("/api/orders", status_code=201)
    def add_order(data: OrderInput, user=Depends(current_user), db=Depends(get_db)):
        order = RepairOrder(created_by=user.id)
        set_order_fields(order, data)
        db.add(order)
        db.commit()
        return order_dict(order)

    @app.get("/api/orders/{order_id}")
    def read_order(order_id: int, user=Depends(current_user), db=Depends(get_db)):
        return order_dict(get_order(db, order_id))

    @app.put("/api/orders/{order_id}")
    def update_order(
        order_id: int, data: OrderInput, user=Depends(current_user), db=Depends(get_db)
    ):
        order = get_order(db, order_id)
        set_order_fields(order, data)
        db.commit()
        return order_dict(order)

    @app.post("/api/orders/{order_id}/complete")
    def complete_order(
        order_id: int,
        data: CompletionInput,
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        order = get_order(db, order_id)
        if order.completed_on:
            raise HTTPException(409, "Заказ уже выполнен")
        completion = data.completed_on or today()
        if completion < order.received_on or completion > today():
            raise HTTPException(422, "Дата выполнения должна быть между датой приёмки и сегодня")
        order.completed_on = completion
        db.commit()
        return order_dict(order)

    @app.post("/api/orders/{order_id}/reopen")
    def reopen_order(order_id: int, user=Depends(current_user), db=Depends(get_db)):
        order = get_order(db, order_id)
        if not order.completed_on:
            raise HTTPException(409, "Заказ уже находится в работе")
        order.completed_on = None
        db.commit()
        return order_dict(order)

    @app.delete("/api/orders/{order_id}", status_code=204)
    def delete_order(order_id: int, user=Depends(admin_user), db=Depends(get_db)):
        db.delete(get_order(db, order_id))
        db.commit()

    @app.get("/api/reports/revenue")
    def revenue(start: date, end: date, user=Depends(current_user), db=Depends(get_db)):
        return revenue_report(db, start, end)

    @app.get("/api/dashboard")
    def dashboard(user=Depends(current_user), db=Depends(get_db)):
        current = today()
        count = lambda *conditions: db.scalar(  # noqa: E731
            select(func.count(RepairOrder.id)).where(*conditions)
        )
        return {
            "today": current,
            "total": count(),
            "pending": count(RepairOrder.completed_on.is_(None)),
            "overdue": count(RepairOrder.completed_on.is_(None), RepairOrder.planned_on < current),
            "completed": count(RepairOrder.completed_on.is_not(None)),
            "month_revenue": money(
                db.scalar(
                    select(func.coalesce(func.sum(RepairOrder.cost_cents), 0)).where(
                        RepairOrder.completed_on.between(current.replace(day=1), current)
                    )
                )
            ),
        }

    @app.get("/api/users")
    def users(user=Depends(admin_user), db=Depends(get_db)):
        return [user_dict(u) for u in db.scalars(select(User).order_by(User.id))]

    @app.post("/api/users", status_code=201)
    def add_user(data: UserInput, user=Depends(admin_user), db=Depends(get_db)):
        new_user = User(
            username=data.username.lower(),
            full_name=data.full_name,
            password_hash=password_hasher.hash(data.password),
            role=data.role,
        )
        db.add(new_user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Такой логин уже занят") from None
        return user_dict(new_user)

    @app.patch("/api/users/{user_id}")
    def activate_user(
        user_id: int,
        data: ActiveInput,
        user=Depends(admin_user),
        db=Depends(get_db),
    ):
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "Пользователь не найден")
        if user.id == target.id and not data.is_active:
            raise HTTPException(409, "Нельзя отключить собственную учётную запись")
        target.is_active = data.is_active
        if not data.is_active:
            db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
        db.commit()
        return user_dict(target)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
