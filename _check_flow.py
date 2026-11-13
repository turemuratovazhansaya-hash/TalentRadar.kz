import io

from PIL import Image

from main import app

c = app.test_client()
print("health", c.get("/api/health").json)

blank = io.BytesIO()
Image.new("RGB", (900, 1200), (255, 255, 255)).save(blank, format="JPEG")
blank.seek(0)

s = c.post("/api/auth/login", json={"email": "student@talentradar.kz", "password": "student123"})
print("student login", s.status_code, (s.json or {}).get("role"), ((s.json or {}).get("profile") or {}).get("name"))
assert s.status_code == 200
auth = {"Authorization": "Bearer " + s.json["token"]}

denied = c.get("/api/radar", headers=auth)
print("student radar", denied.status_code)
assert denied.status_code == 403

bad = c.post(
    "/api/certificates",
    headers=auth,
    data={"cert-title": "Пустой лист", "cert-org": "тест", "cert-date": "12.11.2026", "cert-photo": (blank, "blank.jpg")},
    content_type="multipart/form-data",
)
print("blank cert", bad.status_code, bad.json.get("status"), bad.json.get("reason"))
assert bad.status_code == 201 and bad.json.get("status") == "rejected"

path = r"C:\Users\HP\Downloads\TalentRadar.kz\static\uploads\cert_0aee98adf30343a08a82faad72e7fd5f.jpeg"
with open(path, "rb") as handle:
    payload = io.BytesIO(handle.read())
good = c.post(
    "/api/certificates",
    headers=auth,
    data={
        "cert-title": "Диплом NIS",
        "cert-org": "Назарбаев Интеллектуальная школа",
        "cert-date": "12.11.2026",
        "cert-photo": (payload, "diplom.jpg"),
    },
    content_type="multipart/form-data",
)
print("real cert", good.status_code, good.json.get("status"), good.json.get("score_boost"), good.json.get("reason"))
print("checks", [(item["name"], item["ok"]) for item in good.json.get("checks", [])])
assert good.status_code == 201 and good.json.get("status") == "verified"

u = c.post("/api/auth/login", json={"email": "vuz@talentradar.kz", "password": "vuz123"})
print("uni login", u.status_code, (u.json.get("profile") or {}).get("name"))
assert u.status_code == 200
ut = {"Authorization": "Bearer " + u.json["token"]}
radar = c.get("/api/radar?city=Актобе", headers=ut)
print("radar", radar.status_code, len(radar.json), [item["name"] for item in radar.json])
assert radar.status_code == 200 and radar.json
offer = c.post(f"/api/radar/{radar.json[0]['id']}/offer", headers=ut, json={"title": "Грант 20%", "message": "Ждём вас"})
print("offer", offer.status_code, offer.json)
assert offer.status_code == 200

acts = c.get("/api/activities", headers=auth)
print("activities", acts.status_code, len(acts.json))
assert acts.status_code == 200 and acts.json
join = c.post(f"/api/activities/{acts.json[0]['id']}/join", headers=auth)
print("join", join.status_code, join.json)
assert join.status_code == 200

offers = c.get("/api/offers", headers=auth)
pending = next((item for item in offers.json if item["status"] == "pending"), None)
print("offers", len(offers.json), "pending", None if not pending else pending["id"])
if pending:
    acc = c.post(f"/api/offers/{pending['id']}/accept", headers=auth)
    print("accept", acc.status_code, acc.json)
    assert acc.status_code == 200

reg = c.post(
    "/api/auth/register",
    json={
        "email": "new.student.demo@talentradar.kz",
        "password": "pass1234",
        "role": "student",
        "name": "Айгерим",
        "city": "Семей",
        "grade": 10,
        "track": "Математика / Алгоритмы",
    },
)
print("register", reg.status_code, (reg.json or {}).get("error") or (reg.json or {}).get("role"))
assert reg.status_code == 201
print("OK")
