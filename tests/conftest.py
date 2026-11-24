import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import User
from app.security import password_hasher


@pytest.fixture
def app(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(app):
        with app.state.session_factory() as db:
            password_hash = password_hasher.hash("Password123!")
            db.add_all(
                [
                    User(
                        username="admin",
                        full_name="Администратор",
                        role="admin",
                        password_hash=password_hash,
                    ),
                    User(
                        username="operator",
                        full_name="Оператор",
                        role="operator",
                        password_hash=password_hash,
                    ),
                ]
            )
            db.commit()
        yield app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def login(client):
    def authenticate(username="admin"):
        response = client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": "Password123!",
            },
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        return client

    return authenticate


@pytest.fixture
def order_data():
    return {
        "item_name": "Телевизор",
        "brand": "Samsung",
        "owner_name": "Иванов Иван",
        "owner_phone": "+375 29 123-45-67",
        "cost": "100.10",
        "received_on": "2025-01-01",
        "planned_on": "2025-02-01",
    }
