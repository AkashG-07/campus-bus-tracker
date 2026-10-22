"""Quick automated check of the main flows. Run:  python test_app.py"""
import os
import re
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ALLOWED_DOMAIN"] = "college.edu"

import app as bus_app  # noqa: E402

c = bus_app.app.test_client()


def ok(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        raise SystemExit(1)


# not logged in
ok(c.get("/map").status_code == 302, "map redirects to login when logged out")
ok(c.get("/api/buses").status_code == 401, "API refuses logged-out users")

# registration rules
r = c.post("/register", data={"name": "X", "email": "x@gmail.com", "password": "secret1"})
ok(b"college email" in r.data, "non-college email is rejected")
r = c.post("/register", data={"name": "Asha", "email": "asha@college.edu", "password": "secret1"})
ok(r.status_code == 302, "college email can register")

# student login
r = c.post("/login", data={"email": "asha@college.edu", "password": "secret1"})
ok(r.status_code == 302, "student can log in")
ok(c.get("/map").status_code == 200, "student sees map page")
ok(c.get("/admin").status_code == 403, "student cannot open admin page")
c.get("/logout")

# admin adds a bus
r = c.post("/login", data={"email": "admin@college.local", "password": "admin123"})
ok(r.status_code == 302, "admin can log in")
r = c.post("/admin/buses", data={"name": "Bus 12", "route": "Tambaram - College", "capacity": "40"})
ok(r.status_code == 302, "admin can add a bus")
page = c.get("/admin").data.decode()
token = re.search(r"/driver/([A-Za-z0-9_-]+)", page).group(1)
ok(bool(token), "admin page shows the driver link")
c.get("/logout")

# driver updates (no login, token only)
ok(c.get("/driver/wrongtoken").status_code == 404, "wrong driver token gives 404")
r = c.post(f"/api/driver/{token}/location", json={"lat": 13.0, "lng": 80.2})
ok(r.status_code == 200, "driver can send location")
r = c.post(f"/api/driver/{token}/location", json={"lat": 999, "lng": 80.2})
ok(r.status_code == 400, "bad coordinates are rejected")
r = c.post(f"/api/driver/{token}/seats", json={"occupied": 15})
ok(r.get_json()["seats_available"] == 25, "seat count updates (40 - 15 = 25)")
r = c.post(f"/api/driver/{token}/seats", json={"occupied": 500})
ok(r.get_json()["occupied"] == 40, "occupied seats are capped at capacity")

# student sees the live data
c.post("/login", data={"email": "asha@college.edu", "password": "secret1"})
data = c.get("/api/buses").get_json()
ok(len(data) == 1 and data[0]["lat"] == 13.0 and data[0]["seats_available"] == 0,
   "student sees live location and seat availability")
print("\nAll checks passed.")
