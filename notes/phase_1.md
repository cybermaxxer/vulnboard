# phase 1: auth + core crud (register, login, logout, delete, view users)

phase 0 got a vulnerable flask app booting inside docker, talking to mysql, with debug mode hardcoded on and nothing bound past `127.0.0.1`. phase 1 is where the app actually does something: users can register, log in, log out, view their session state, delete their own account, and (intentionally, for lab purposes) browse every user's row including plaintext passwords. six files carry that: `app/__init__.py`, `app/auth.py`, `app/db.py`, `init.sql`, and the templates (`index.html`, `login.html`, `register.html`, `delete.html`, `users.html`).

`upload.html` and `see.html` exist as empty files and `index.html` already links to `/upload` and `/see`, but neither route exists yet. that's not a bug, that's phase 2 (the posts feature). those links are dead for now.

## database shape: `init.sql`

```sql
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    user_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

`users` only has `id`, `username`, `password`, no `email` column, that matters later because an earlier draft of `users.html` tried to render `user.email` and it doesn't exist in the schema, fixed by just not selecting or rendering it.

`posts` already exists in the schema even though nothing in phase 1 touches it. that's deliberate, the table's there so phase 2 doesn't need a migration, it just needs routes. `ON DELETE CASCADE` on `user_id` means if a user row gets deleted, every post tied to that `user_id` gets deleted automatically by mysql itself, no python cleanup code needed, the database enforces it at the foreign key level.

`docker-entrypoint-initdb.d/init.sql` (from the compose mount in phase 0) only runs once, the first time the `db` container initializes its data volume. if you already have a running mysql volume from phase 0 and then add or edit `init.sql`, it will not re run automatically, mysql only looks at that folder on a fresh, empty data directory. worth remembering if a schema change doesn't seem to take effect.

## app/__init__.py: routes

```python
from flask import Flask, render_template, request, redirect, url_for, session
```

explicit imports, every name `__init__.py` actually calls (`render_template`, `redirect`, `url_for`, `session`) is named here, nothing pulled in silently. mental model: this is a whitelist, you can read this one line and know exactly what flask surface this file is allowed to touch. the alternative, `from flask import *`, would also work, flask exports all these same names, but it dumps dozens of names into the module's namespace at once with no record of which ones are actually used, harder to audit six months later. small thing, but it's the difference between "i can see what this file depends on" and "i'd have to grep to find out."

one thing worth double checking whenever you add a new route: `current_app` is not in that import line. it's not needed here because no route in `__init__.py` calls it directly, it's only used inside `db.py`, which imports it on its own. if a future route in this file ever needs `current_app` (say, reading a config value directly instead of through `get_db()`), it has to be added to this import line explicitly, it won't come along for free.

routes registered:

| route | methods | does |
|---|---|---|
| `/` | GET | renders `index.html`, which branches on `session.get('username')` to show either a logged in nav or login/register links |
| `/login` | GET | renders the login form |
| `/login` | POST | calls `handle_login()` in `auth.py` |
| `/register` | GET | renders the registration form |
| `/register` | POST | calls `handle_registration()` in `auth.py` |
| `/logout` | GET | clears the whole session, redirects to `/` |
| `/delete` | GET | renders the delete account form, only usable while logged in |
| `/delete` | POST | calls `delete_account()` in `auth.py` |
| `/users` | GET | pulls every row from `users` (id, username, password) and renders them in `users.html`, no login required |

`/users` having no auth check and printing plaintext passwords is intentional for the lab, it's the clearest possible demonstration of why passwords need hashing: the column holds whatever was typed at registration, in the clear, and this route just reads it back.

each `@app.route(...)` decorator runs exactly once, at boot, inside `create_app()`. it doesn't re execute per request, it just stores a reference to the function in flask's url map. what runs per request is flask looking the path up in that already built map and calling the stored function. same mental model as phase 0's `index` route, nothing new here, just more entries in the map now.

## app/auth.py: the actual logic

### registration

```python
def handle_registration():
    username = request.form.get("username")
    password = request.form.get("password")
    if not username or not password:
        return "Username and password are required.", 400
    does_exist = check_user_exists(username)
    if does_exist:
        return "Username already exists.", 400
    create_user(username, password)
    return redirect(url_for("login"))
```

straightforward flow: pull form fields, reject if either is missing, reject if the username's taken, otherwise insert and redirect to `/login`. `check_user_exists()` and `create_user()` both build their sql with f strings:

```python
sql_query = f"SELECT * FROM users WHERE username = '{username}'"
sql_query = f"INSERT INTO users (username, password) VALUES ('{username}', '{password}')"
```

this is the planted sql injection. `username` and `password` go straight from the request into the query string, no parameterization, no escaping. the fix would be swapping to a parameterized query, `cursor.execute("SELECT * FROM users WHERE username = %s", (username,))`, where the driver sends the value separately from the query structure instead of splicing it into the sql text. that's phase 2+ hardening, not phase 1, phase 1's job is to have the vuln actually there and working.

cybersec angle, concretely: a `username` of `' OR '1'='1` turns the login query's `WHERE username = '...' AND password = '...'` into something that's true for every row, because the attacker closed the quote early and injected their own boolean logic into the query structure itself. the database can't tell the difference between "the developer's sql" and "the developer's sql plus whatever the attacker appended," it all arrives as one string and gets parsed as one query. defense is always the same idea regardless of language or db: never let user input become part of the query's structure, only ever let it be a value inside a slot the query already defined.

### login

```python
def get_user_by_credentials(username, password):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    sql_query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    cursor.execute(sql_query)
    user = cursor.fetchone()
    cursor.close()
    return user

def handle_login():
    username = request.form.get("username")
    password = request.form.get("password")
    if not username or not password:
        return "Username and password are required.", 400
    user = get_user_by_credentials(username, password)
    if user is None:
        return "Invalid username or password.", 401
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return redirect(url_for("index"))
```

the auth decision lives entirely inside the sql query, both username and password are matched in the `WHERE` clause, and python just checks whether `fetchone()` returned a row or `None`. there's no separate python side password comparison anywhere in this flow, which matters for the injection case above: if the `WHERE` clause gets manipulated to always evaluate true, `fetchone()` returns a real row regardless of what password was typed, and python has no second check to catch that, it trusts the db's answer completely.

on success, two keys get written into `session`: `user_id` and `username`. `session` in flask isn't server side storage by default, it's a cookie, signed (not encrypted) using `SECRET_KEY` from `config.py`. signed means the client can read the cookie's contents (base64 decode it and you'll see the json), but can't modify it undetected, because flask recomputes the signature on every incoming request and rejects the cookie if it doesn't match. this is exactly why `SECRET_KEY` defaulting to `"default-fallback-key"` in phase 0's `config.py` is a real vuln, not cosmetic: anyone who knows the key can forge a valid signature for any session content they want, including a fake `user_id` for a user they've never authenticated as.

### logout

```python
def handle_logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect(url_for("index"))
```

defined in `auth.py` but not actually wired up, `__init__.py`'s `/logout` route calls `session.clear()` directly instead of calling this function. both approaches end at the same result here (only two keys exist in session right now, `clear()` and popping both land identically) but `handle_logout()` as written is currently dead code, nothing calls it. worth a decision for phase 2: either wire `/logout` to call it (keeps all session mutation logic inside `auth.py`, consistent with how every other route delegates), or just delete it if `session.clear()` in `__init__.py` is the intended final form. not a bug, just an inconsistency worth resolving before it causes confusion later (say if session grows a third key and only one of the two logout paths gets updated).

### delete account

```python
def delete_account():
    user_id = session.get("user_id")
    password = request.form.get("password")
    if not password:
        return "Password is required to delete your account.", 400
    if not user_id:
        return "You must be logged in to delete your account.", 401
    if not session.get("username"):
        return "You must be logged in to delete your account.", 401
    user = get_user_by_credentials(session.get("username"), password)
    if user is None:
        return "Invalid password. Account deletion failed.", 401
    if user["id"] != user_id:
        return "You can only delete your own account.", 403
    db = get_db()
    cursor = db.cursor()
    sql_query = f"DELETE FROM users WHERE id = {user_id}"
    cursor.execute(sql_query)
    db.commit()
    cursor.close()
    session.clear()
    return redirect(url_for("index"))
```

order of checks matters here, each one is a distinct failure mode with its own status code: `400` if the form didn't even include a password, `401` if there's no session at all (not logged in), `401` again if the submitted password doesn't match what's on file for that username (reuses `get_user_by_credentials`, same function login uses, so the credential check logic only lives in one place), `403` if somehow the session's `user_id` doesn't match the row that query just authenticated as (defense in depth against session tampering, this is the one check that doesn't trust the session blindly). only after all four pass does the actual `DELETE` run.

`sql_query = f"DELETE FROM users WHERE id = {user_id}"` looks like it could be another injection point, but `user_id` here never came from user input, it came from `session.get("user_id")`, which was set server side during `handle_login()` from a value flask already authenticated. an attacker would need a forged session cookie to control this value at all, which loops back to the `SECRET_KEY` issue above, this isn't a new vuln, it's the same one surfacing in a second place.

## templates: what changed from raw html to jinja

`index.html`, `login.html`, `delete.html` all use `{% if session.get('username') %}` to branch between a logged in and logged out view. this works because flask automatically makes `session` available inside every template's context, no explicit passing required, same way `request` is automatically available. `users.html` is the one template that receives explicit data: `render_template("users.html", users=users)` passes the query results in by name, and the template loops over it with `{% for user in users %}`.

## boot sequence, phase 1 additions

phase 0 ended at: container boots, `create_app()` runs, routes register, server listens. phase 1 adds what happens per request now that routes actually do things:

1. request hits `/register` (POST) → flask finds it in the url map → calls `register_post()` → that calls `handle_registration()` in `auth.py`
2. `handle_registration()` calls `get_db()` (via `check_user_exists`), first call this request, opens a fresh mysql connection, stores it on `g.db`
3. insert runs, commits, cursor closes (connection itself stays open on `g` for the rest of this request)
4. response returns, flask's teardown fires (`close_db`, registered back in phase 0), `g.db` gets popped and closed
5. next request gets a brand new `g`, brand new connection, nothing carries over, by design, `g` never survives past one request

same per request lifecycle on `/login`, `/delete`, `/users`, the only thing that changes between them is which function runs and what sql it issues.

## known gaps at end of phase 1

- `/upload` and `/see` are linked from `index.html` but don't exist yet, posts feature is phase 2
- `handle_logout()` in `auth.py` is dead code, `/logout` uses `session.clear()` directly instead
- sql injection is live and intentional in `check_user_exists`, `create_user`, `get_user_by_credentials`, three different f string queries, all exploitable the same way
- `/users` has no authentication and exposes every password in plaintext, intentional, this is the "why hash passwords" lab demo
- `DEBUG = True` and the default `SECRET_KEY` from phase 0 are both still live, phase 1 just gave them more surface area to matter on (session forgery via weak `SECRET_KEY` is a phase 1 concern even though the key itself was set in phase 0)
