from server import app

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