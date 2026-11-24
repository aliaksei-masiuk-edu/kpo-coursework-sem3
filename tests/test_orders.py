from datetime import timedelta

import pytest

from app.main import create_app
from app.services import today


def create(client, data):
    response = client.post("/api/orders", json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_full_order_lifecycle_and_permissions(client, login, order_data):
    assert client.get("/api/orders").status_code == 401
    login("operator")
    order = create(client, order_data)
    order_id = order["id"]
    assert order["cost"] == "100.10"
    assert order["is_overdue"] is True
    changed = client.put(f"/api/orders/{order_id}", json={**order_data, "brand": "LG"})
    assert changed.json()["brand"] == "LG"
    assert client.get(f"/api/orders/{order_id}").json()["brand"] == "LG"
    complete = client.post(f"/api/orders/{order_id}/complete", json={"completed_on": "2025-02-03"})
    assert complete.status_code == 200
    assert complete.json()["is_completed"] is True
    assert complete.json()["is_overdue"] is False
    assert client.post(f"/api/orders/{order_id}/complete", json={}).status_code == 409
    assert client.delete(f"/api/orders/{order_id}").status_code == 403
    assert client.post(f"/api/orders/{order_id}/reopen").json()["completed_on"] is None
    assert client.post(f"/api/orders/{order_id}/reopen").status_code == 409
    login()
    assert client.delete(f"/api/orders/{order_id}").status_code == 204
    assert client.get(f"/api/orders/{order_id}").status_code == 404


def test_pending_sort_boundary_search_and_pagination(client, login, order_data):
    login()
    future = create(client, {**order_data, "planned_on": (today() + timedelta(days=2)).isoformat()})
    due_today = create(client, {**order_data, "planned_on": today().isoformat()})
    overdue = create(
        client, {**order_data, "planned_on": (today() - timedelta(days=1)).isoformat()}
    )
    oldest = create(client, order_data)
    completed = create(client, order_data)
    client.post(f"/api/orders/{completed['id']}/complete", json={})
    result = client.get("/api/orders?status=pending").json()
    assert [o["id"] for o in result["items"]] == [
        oldest["id"],
        overdue["id"],
        due_today["id"],
        future["id"],
    ]
    assert due_today["is_overdue"] is False
    assert client.get("/api/orders?status=overdue").json()["total"] == 2
    page = client.get("/api/orders?status=pending&offset=1&limit=2").json()
    assert page["total"] == 4
    assert len(page["items"]) == 2
    assert client.get("/api/orders?search=иванов").json()["total"] == 5
    assert client.get("/api/orders", params={"search": f"#{future['id']}"}).json()["total"] == 1
    assert (
        client.get("/api/orders", params={"search": "#999999999999999999999999"}).json()["total"]
        == 0
    )
    assert client.get("/api/orders?search=%25").json()["total"] == 0
    assert client.get("/api/orders?status=unknown").status_code == 422


def test_revenue_exact_money_inclusive_dates_and_reopen(client, login, order_data):
    login()
    for amount, completion in [
        ("0.10", "2025-02-01"),
        ("0.20", "2025-02-03"),
        ("999.99", "2025-01-31"),
        ("888.88", "2025-02-04"),
    ]:
        order = create(client, {**order_data, "cost": amount})
        client.post(f"/api/orders/{order['id']}/complete", json={"completed_on": completion})
    create(client, {**order_data, "cost": "777.77"})
    report = client.get("/api/reports/revenue?start=2025-02-01&end=2025-02-03").json()
    assert report["total"] == "0.30"
    assert report["count"] == 2
    assert len(report["items"]) == 2
    one_day = client.get("/api/reports/revenue?start=2025-02-01&end=2025-02-01").json()
    assert one_day["total"] == "0.10"
    assert client.get("/api/reports/revenue?start=2025-02-03&end=2025-02-01").status_code == 422
    assert (
        client.get("/api/reports/revenue?start=2025-05-01&end=2025-05-03").json()["total"] == "0.00"
    )
    client.post(f"/api/orders/{report['items'][0]['id']}/reopen")
    assert (
        client.get("/api/reports/revenue?start=2025-02-01&end=2025-02-03").json()["total"] == "0.20"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("cost", "-1"),
        ("cost", "1.001"),
        ("cost", "NaN"),
        ("cost", "100000000.00"),
        ("owner_phone", "abcdefg"),
        ("owner_name", " "),
        ("planned_on", "2024-12-31"),
        ("received_on", "not-a-date"),
        ("received_on", "2099-01-01"),
        ("unexpected", "field"),
    ],
)
def test_invalid_order_rejected(client, login, order_data, field, value):
    login()
    assert client.post("/api/orders", json={**order_data, field: value}).status_code == 422
    assert client.get("/api/orders").json()["total"] == 0


def test_completion_and_edit_date_validation(client, login, order_data):
    login()
    order = create(client, order_data)
    path = f"/api/orders/{order['id']}"
    for date in ["2024-12-31", "2099-01-01"]:
        assert client.post(f"{path}/complete", json={"completed_on": date}).status_code == 422
    assert client.post(f"{path}/complete", json={"completed_on": "2025-01-10"}).status_code == 200
    assert client.put(path, json={**order_data, "received_on": "2025-01-11"}).status_code == 422


def test_dashboard_and_persistence(client, app, login, order_data):
    from fastapi.testclient import TestClient

    login()
    first = create(client, {**order_data, "cost": "12.34"})
    create(client, {**order_data, "planned_on": today().isoformat()})
    client.post(f"/api/orders/{first['id']}/complete", json={})
    dashboard = client.get("/api/dashboard").json()
    assert (
        dashboard["total"],
        dashboard["pending"],
        dashboard["overdue"],
        dashboard["completed"],
    ) == (2, 1, 0, 1)
    assert dashboard["month_revenue"] == "12.34"
    second_app = create_app(str(app.state.engine.url))
    with TestClient(second_app) as restarted:
        response = restarted.post(
            "/api/auth/login", json={"username": "admin", "password": "Password123!"}
        )
        assert response.status_code == 200
        assert restarted.get("/api/orders").json()["total"] == 2
