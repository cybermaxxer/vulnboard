# sensitive data exposure: plaintext passwords and an open /users route

vulnboard stores passwords as plain text, and `/users` prints every one of them to anyone who asks, logged in or not. no sqli, no tricks, one GET request.

| piece | where | what's wrong |
|---|---|---|
| plaintext storage | `users.password` column, `logic/auth.py` | the db holds real passwords, not hashes |
| open user dump | `/users` in `logic/__init__.py`, `users.html` | no login check, prints the password column |
| weak config defaults | `logic/config.py` | known fallback secret key, hardcoded `DEBUG = True` |

## 1. plaintext password storage

the schema in `init.sql` has no hash column and no salt:

```sql
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
);
```

registration writes whatever the user typed straight into it:

```python
sql_query = f"INSERT INTO users (username, password) VALUES ('{username}', '{password}')"
```

and login compares the raw value inside the query:

```python
sql_query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
```

why this matters: a hash is a one way function. you can turn a password into a hash, but you can't turn the hash back into the password. so a stolen table of hashes still costs the attacker real work per password. a stolen table of plaintext costs nothing: the database *is* the password list. one leak, every account, and every other site where those users reused the same password.

## 2. /users: the password list, no login needed

the route has no session check:

```python
@app.route("/users")
def view_users():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, username, password FROM users")
    users = cursor.fetchall()
    cursor.close()
    return render_template("users.html", users=users)
```

the template prints every field it gets:

```html
{% for user in users %}
    <li>user_id: {{ user.id }}, username: {{ user.username }}, password: {{ user.password }}</li>
{% endfor %}
```

`index.html` even links to it from the logged out menu, so you don't need to guess the url.

this is broken access control and sensitive data exposure stacked together. the query asks for the password column when nothing on the page needs it, and the route never asks who's calling.

### reproduce

```bash
curl -i http://127.0.0.1:5000/users
```

- `curl` sends a plain HTTP GET
- `-i` includes the response headers in the output, so you can see the status line
- no `-b` or cookie flag on purpose: sending no session at all is the proof that no login is needed

expected: `200 OK` and a list shaped like this, with whatever accounts exist on your instance:

```text
user_id: 1, username: <name>, password: <the exact password that user registered with>
```

the evidence for this one is still owed: paste the real response from a fresh container here before calling it done.

## 3. config problems that belong in the same bucket

**known fallback secret key.** `logic/config.py` reads `FLASK_SECRET_KEY` from `.env` but falls back to a hardcoded string:

```python
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "default-fallback-key")
```

flask signs the session cookie with this key. if the env var is ever missing, the key is a string that sits in the public repo, and anyone can sign a cookie claiming `user_id = 1`. the cookie is signed, not encrypted, so the contents are readable anyway.

**hardcoded debug mode.** `DEBUG = True` is set in the same file. the idea is that an unhandled exception returns werkzeug's traceback page, which leaks file paths, source lines and sometimes config values.

one thing i haven't confirmed: the `flask` cli resets `app.debug` from the `FLASK_DEBUG` environment variable after the app loads (flask 2.2 and later), so `DEBUG = True` in the config class may not turn the debugger on by itself. quick test: log in with a password of `'`, which breaks the sql query and raises an unhandled error. a traceback page means debug is live. a plain "internal server error" means it isn't, and the fix for the lab is setting `FLASK_DEBUG=1` in `.env`.

## impact

| attacker action | result |
|---|---|
| GET `/users` | every username and password, no account needed |
| log in with a listed pair | full access to that account |
| try the same pairs on other services | credential reuse |
| forge a session (only if the fallback key is live) | log in as any user without a password |

## how it gets defended (not implemented, this repo is exploitation only)

- hash passwords with `werkzeug.security.generate_password_hash` and check them with `check_password_hash`, so the db never holds a usable password
- delete `/users`, or put it behind an admin check, and never select the password column for display
- no fallback for `SECRET_KEY`: crash on boot if it's missing
- `DEBUG` off by default, read from the environment

## evidence status

| check | status |
|---|---|
| `users.password` is plaintext (read `init.sql`, `auth.py`) | confirmed from code |
| `/users` has no session check | confirmed from code |
| `curl` output from a running container | still to capture |
| debug traceback actually shows up | still to verify |