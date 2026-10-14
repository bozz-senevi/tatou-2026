
from types import SimpleNamespace
from server import document_lookup_query
from werkzeug.security import generate_password_hash
from server import app, credentials_valid


def test_healthz_route():
    client = app.test_client()
    resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["message"] == "The server is up and running."


def test_login_missing_credentials():
    client = app.test_client()

    resp = client.post("/api/login", json={})

    assert resp.status_code == 400
    assert resp.is_json
    assert resp.get_json()["error"] == "email and password are required"


def test_login_missing_password():
    client = app.test_client()

    resp = client.post("/api/login", json={
        "email": "student@example.com"
    })

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "email and password are required"


def test_credentials_valid_correct_password():
    row = SimpleNamespace(
        hpassword=generate_password_hash("SecurePass123")
    )

    assert credentials_valid(row, "SecurePass123") is True


def test_credentials_valid_wrong_password():
    row = SimpleNamespace(
        hpassword=generate_password_hash("SecurePass123")
    )

    assert credentials_valid(row, "WrongPassword") is False


def test_credentials_valid_unknown_user():
    assert credentials_valid(None, "SecurePass123") is False

def test_document_lookup_requires_owner():
    query = document_lookup_query()
    sql = str(query)

    assert "WHERE id = :id AND ownerid = :uid" in sql

def test_create_app_initializes_flask():
    from server import create_app
    from flask import Flask

    new_app = create_app()

    assert isinstance(new_app, Flask)