"""Campus Bus Tracker - version 1.

Features:
  1. Login for students and admins (students can optionally be limited to a college email domain)
  2. Live bus locations on a map
  3. Seat availability per bus
"""
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "bus.db"))
# If set (e.g. "stjosephs.ac.in"), only emails from this domain can register as students.
ALLOWED_DOMAIN = os.environ.get("ALLOWED_DOMAIN", "").strip().lower()
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@college.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")


# ---------- database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('student', 'admin'))
        );
        CREATE TABLE IF NOT EXISTS buses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            route TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            occupied INTEGER NOT NULL DEFAULT 0,
            lat REAL,
            lng REAL,
            updated_at TEXT,
            driver_token TEXT NOT NULL UNIQUE
        );
        """
    )
    has_admin = db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone()
    if not has_admin:
        db.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
            ("Administrator", ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD)),
        )
    db.commit()
    db.close()


# ---------- auth helpers ----------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="login required"), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def bus_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "route": row["route"],
        "capacity": row["capacity"],
        "occupied": row["occupied"],
        "seats_available": row["capacity"] - row["occupied"],
        "lat": row["lat"],
        "lng": row["lng"],
        "updated_at": row["updated_at"],
    }


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- pages: auth ----------
@app.route("/")
def index():
    return redirect(url_for("map_page" if "user_id" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or "@" not in email or len(password) < 6:
            flash("Enter your name, a valid email, and a password of at least 6 characters.")
        elif ALLOWED_DOMAIN and not email.endswith("@" + ALLOWED_DOMAIN):
            flash("Please use your college email address (@%s)." % ALLOWED_DOMAIN)
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'student')",
                    (name, email, generate_password_hash(password)),
                )
                db.commit()
                flash("Account created. Please log in.")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.")
    return render_template("register.html", domain=ALLOWED_DOMAIN)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(url_for("admin_page" if user["role"] == "admin" else "map_page"))
        flash("Wrong email or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- pages: student map ----------
@app.route("/map")
@login_required
def map_page():
    return render_template("map.html")


@app.route("/api/buses")
@login_required
def api_buses():
    rows = get_db().execute("SELECT * FROM buses ORDER BY name").fetchall()
    return jsonify([bus_to_dict(r) for r in rows])


# ---------- pages: admin ----------
@app.route("/admin")
@admin_required
def admin_page():
    rows = get_db().execute("SELECT * FROM buses ORDER BY name").fetchall()
    buses = [dict(bus_to_dict(r), driver_token=r["driver_token"]) for r in rows]
    return render_template("admin.html", buses=buses)


@app.route("/admin/buses", methods=["POST"])
@admin_required
def admin_add_bus():
    name = request.form.get("name", "").strip()
    route = request.form.get("route", "").strip()
    try:
        capacity = int(request.form.get("capacity", ""))
    except ValueError:
        capacity = 0
    if not name or not route or capacity < 1 or capacity > 200:
        flash("Enter a bus name, a route, and a capacity between 1 and 200.")
    else:
        db = get_db()
        db.execute(
            "INSERT INTO buses (name, route, capacity, driver_token) VALUES (?, ?, ?, ?)",
            (name, route, capacity, secrets.token_urlsafe(16)),
        )
        db.commit()
        flash("Bus added.")
    return redirect(url_for("admin_page"))


@app.route("/admin/buses/<int:bus_id>/delete", methods=["POST"])
@admin_required
def admin_delete_bus(bus_id):
    db = get_db()
    db.execute("DELETE FROM buses WHERE id = ?", (bus_id,))
    db.commit()
    flash("Bus deleted.")
    return redirect(url_for("admin_page"))


# ---------- driver (no login; uses a secret link given by the admin) ----------
def bus_by_token(token):
    row = get_db().execute("SELECT * FROM buses WHERE driver_token = ?", (token,)).fetchone()
    if row is None:
        abort(404)
    return row


@app.route("/driver/<token>")
def driver_page(token):
    bus = bus_by_token(token)
    return render_template("driver.html", bus=bus_to_dict(bus), token=token)


@app.route("/api/driver/<token>/location", methods=["POST"])
def driver_location(token):
    bus = bus_by_token(token)
    data = request.get_json(silent=True) or {}
    try:
        lat, lng = float(data["lat"]), float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="lat and lng required"), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify(error="coordinates out of range"), 400
    db = get_db()
    db.execute("UPDATE buses SET lat=?, lng=?, updated_at=? WHERE id=?", (lat, lng, now_iso(), bus["id"]))
    db.commit()
    return jsonify(ok=True)


@app.route("/api/driver/<token>/seats", methods=["POST"])
def driver_seats(token):
    bus = bus_by_token(token)
    data = request.get_json(silent=True) or {}
    try:
        occupied = int(data["occupied"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="occupied (number) required"), 400
    occupied = max(0, min(bus["capacity"], occupied))
    db = get_db()
    db.execute("UPDATE buses SET occupied=?, updated_at=? WHERE id=?", (occupied, now_iso(), bus["id"]))
    db.commit()
    return jsonify(occupied=occupied, seats_available=bus["capacity"] - occupied)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
