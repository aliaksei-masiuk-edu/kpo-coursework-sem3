from datetime import timedelta

from sqlalchemy import select

from app.models import LoginSession
from app.security import utcnow


def test_login_logout_csrf_and_cookie_flags(client, login, order_data):
    assert (
        client.post("/api/auth/login", json={"username": "nope", "password": "wrong"}).status_code
        == 401
    )
    assert (
        client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code
        == 401
    )
    login()
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert "password_hash" not in me.json()["user"]
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/orders", json=order_data).status_code == 403
    client.headers["X-CSRF-Token"] = me.json()["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "Password123!"}
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert me.headers["cache-control"] == "no-store"


def test_expired_session_denied(client, app, login):
    login()
    with app.state.session_factory() as db:
        session = db.scalar(select(LoginSession))
        session.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/orders").status_code == 401


def test_admin_user_management_and_session_revocation(client, login):
    login("operator")
    assert client.get("/api/users").status_code == 403
    assert (
        client.post(
            "/api/users",
            json={
                "username": "staff",
                "full_name": "Новый сотрудник",
                "password": "Password123!",
                "role": "admin",
            },
        ).status_code
        == 403
    )
    login()
    data = {
        "username": "NewStaff",
        "full_name": "Новый сотрудник",
        "password": "Password123!",
        "role": "operator",
    }
    response = client.post("/api/users", json=data)
    assert response.status_code == 201
    new_id = response.json()["id"]
    assert response.json()["username"] == "newstaff"
    assert client.post("/api/users", json=data).status_code == 409
    assert client.patch("/api/users/1", json={"is_active": False}).status_code == 409
    login("newstaff")
    old_token = client.cookies.get("service_session")
    login()
    assert client.patch(f"/api/users/{new_id}", json={"is_active": False}).status_code == 200
    admin_token = client.cookies.get("service_session")
    client.cookies.clear()
    client.cookies.set("service_session", old_token)
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/login", json={"username": "newstaff", "password": "Password123!"}
        ).status_code
        == 401
    )
    client.cookies.set("service_session", admin_token)
    assert client.patch(f"/api/users/{new_id}", json={"is_active": True}).status_code == 200
    assert (
        client.post(
            "/api/auth/login", json={"username": "newstaff", "password": "Password123!"}
        ).status_code
        == 200
    )


def test_frontend_and_openapi_available(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert "/api/reports/revenue" in client.get("/openapi.json").json()["paths"]
