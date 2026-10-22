# Campus Bus Tracker

A web app that lets students of a college see where college buses are right now and how many seats are free. Admins manage the buses.

This is **version 1**. It covers three features:

1. **Login** for students and admins (students can be limited to a college email domain)
2. **Live bus locations** on a map, refreshed every 5 seconds
3. **Seat availability** for each bus

## Tech stack

- Python, Flask (backend)
- SQLite (database)
- HTML, CSS, JavaScript (frontend)
- Leaflet + OpenStreetMap (map)

## How it works

- **Admin** logs in, adds buses (name, route, capacity). Each bus gets a private driver link.
- **Driver** opens that link on a phone, taps "Start sharing my location", and uses +/- to update occupied seats.
- **Students** log in and see all buses on a live map with seats available.

The browser asks the server for `/api/buses` every 5 seconds (polling) and moves the markers.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

- Default admin: `admin@college.local` / `admin123` (change it before real use, see below)
- Students register at `/register`

### Try the demo in 2 minutes

1. Log in as admin, add a bus, copy its driver link.
2. Open the driver link in a second tab and press **Simulate movement**.
3. Register a student account in a private window and watch the bus move on the map.

### Settings (environment variables)

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs login sessions. Set a long random value. | dev value |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | First admin account (created only if no admin exists) | admin@college.local / admin123 |
| `ALLOWED_DOMAIN` | Only this email domain can register, e.g. `yourcollege.ac.in` | any email |
| `DB_PATH` | Location of the SQLite file | `bus.db` |

Example: `ALLOWED_DOMAIN=yourcollege.ac.in SECRET_KEY=change-me python app.py`

### Test

```bash
python test_app.py
```

## Project structure

```
app.py            routes, database, login logic
templates/        pages: login, register, map, admin, driver
test_app.py       automated checks for the main flows
```

## Known limitations (future scope)

- Phone GPS needs HTTPS (or localhost), so real deployment needs hosting with HTTPS
- No CSRF protection on forms yet
- Seat count is updated manually by the driver
- Not built yet: smart attendance on boarding, emergency alerts to administration, route details page, push notifications
