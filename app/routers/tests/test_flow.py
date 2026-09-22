def _staff_headers(client):
    client.post(
        "/auth/register-staff",
        json={"email": "guard@school.example", "password": "correct-horse-1", "invite_code": "test-invite-code"},
    )
    r = client.post("/auth/login", json={"email": "guard@school.example", "password": "correct-horse-1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _device_headers(client, staff_headers):
    code = client.post("/devices/pairing-codes", headers=staff_headers).json()["code"]
    r = client.post("/devices/register", json={"pairing_code": code, "location": "Коридор 2 этаж"})
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


def test_staff_register_and_login(client):
    headers = _staff_headers(client)
    assert "Authorization" in headers


def test_device_pairing_and_event_flow(client):
    staff = _staff_headers(client)
    dev_headers, dev_body = _device_headers(client, staff)
    assert dev_body["device_id"]

    r = client.post("/events", json={"trigger_word": "дурак", "confidence": 0.8}, headers=dev_headers)
    assert r.status_code == 201
    event_id = r.json()["id"]

    # дедупликация: то же слово сразу же не создаёт новое событие
    r2 = client.post("/events", json={"trigger_word": "дурак", "confidence": 0.9}, headers=dev_headers)
    assert r2.status_code == 200
    assert r2.json()["deduplicated"] is True
    assert r2.json()["id"] == event_id

    r3 = client.get("/events", headers=staff)
    assert r3.status_code == 200
    assert len(r3.json()) == 1

    r4 = client.patch(f"/events/{event_id}", json={"status": "handled"}, headers=staff)
    assert r4.status_code == 200
    assert r4.json()["status"] == "handled"


def test_event_rejects_unknown_trigger(client):
    staff = _staff_headers(client)
    dev_headers, _ = _device_headers(client, staff)
    r = client.post("/events", json={"trigger_word": "случайное слово", "confidence": 0.5}, headers=dev_headers)
    assert r.status_code == 422


def test_event_rejects_extra_fields_like_audio_or_text(client):
    """Схема EventIn с extra='forbid' — сервер физически не примет аудио/текст."""
    staff = _staff_headers(client)
    dev_headers, _ = _device_headers(client, staff)
    r = client.post(
        "/events",
        json={"trigger_word": "помощь", "confidence": 0.7, "transcript": "секретный разговор"},
        headers=dev_headers,
    )
    assert r.status_code == 422


def test_device_cannot_access_staff_endpoints(client):
    staff = _staff_headers(client)
    dev_headers, _ = _device_headers(client, staff)
    r = client.get("/events", headers=dev_headers)
    assert r.status_code == 403


def test_expired_pairing_code_rejected(client):
    staff = _staff_headers(client)
    r = client.post("/devices/register", json={"pairing_code": "ZZZZ-ZZZZ", "location": "x"})
    assert r.status_code == 403