# phase 1: auth, posts, sqli (end of phase)

phase 0 was just plumbing. phase 1 is where the app actually does something: register, login, post, browse, delete account, plus the sqli that's the whole point of this project. five new pieces: `app/auth.py`, the new routes in `app/__init__.py`, `init.sql`, the templates, and a tweak to `docker-compose.yml` to seed the db on first boot.

## init.sql, the schema

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
    image_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

`password VARCHAR(255) NOT NULL`, plaintext, no hashing column, no salt. that's deliberate for this phase, auth bypass via sqli is the target, not credential storage hygiene, but worth remembering this is a second, separate vuln sitting right next to the sqli one: if the db ever leaked through any path, every password is sitting there in the clear.

`ON DELETE CASCADE` on `posts.user_id` means mysql itself deletes a user's posts automatically when the user row gets deleted, no app code needed for that part. the comment in `auth.py`'s `delete_account()` references this directly: it still runs its own explicit `DELETE FROM posts WHERE user_id = %s` first, belt and suspenders, since the cascade should already cover it.

`docker-compose.yml` mounts this file now:

```yaml
volumes:
  - ./init.sql:/docker-entrypoint-initdb.d/init.sql
```

mysql's official image runs anything in `/docker-entrypoint-initdb.d/` automatically, but only on first boot, same rule as the root password setup from phase 0, only fires against an empty data directory. if the schema changes later, a fresh volume (or `docker compose down -v`) is needed to re-trigger it, editing `init.sql` alone won't touch an already-initialized db.

## app/auth.py, the vulnerable core

```python
def check_user_exists(username):
    sql_query = f"SELECT * FROM users WHERE username = '{username}'"
```

raw f-string straight into the query, no parameterization. same pattern repeats in `create_user`, `get_user_by_credentials`, `delete_account`, and `get_username_by_id` over in `db.py`. every single one of these is an injection point, not just the login flow, that's wider than the original plan called for, worth remembering when testing payloads later, `/users`, `/see`, and `/delete` are all exploitable too, not only `/login`.

the actual auth bypass lives here:

```python
def get_user_by_credentials(username, password):
    sql_query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    cursor.execute(sql_query)
    user = cursor.fetchone()
    return user

def handle_login():
    user = get_user_by_credentials(username, password)
    if user is None:
        return "Invalid username or password.", 401
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return redirect(url_for("index"))
```

the comment nails it: "auth decision now lives entirely in sql." there's no python-side password comparison happening anywhere, `handle_login` just trusts whatever row mysql hands back. `username = 'admin'--` in the username field, anything in the password field, comments out the password check entirely, comes back with the `admin` row, logs in as them. textbook.

one thing to flag: `get_user_by_credentials` is reused by both `handle_login` and `delete_account`, meaning the same sqli surface exists on account deletion too, `' OR '1'='1' --` as a "password" during delete could plausibly authenticate as the wrong account, worth testing once the session's up.

## app/__init__.py, the new routes

all the usual flask route registration from phase 0, same pattern, decorator runs once at boot and maps url → function, nothing new conceptually there. what's new is the actual handlers:

```python
@app.route("/users")
def view_users():
    cursor.execute("SELECT id, username, password FROM users")
```

`/users` is a plaintext password dump, open to anyone, logged in or not, no auth check on this route at all. not even sqli-dependent, it's just an unauthenticated leak by design, worth noting separately from the injection vulnerabilities since it's a different bug class (broken access control, not injection).

```python
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if file:
        sql_query = f"INSERT INTO posts (title, content, image_path, user_id) VALUES ('{title}', '{content}', 'uploads/{file.filename}', {session['user_id']})"
        cursor.execute(sql_query)
        db.commit()
        cursor.close()
        return f"File '{file.filename}' uploaded successfully!"
```

this one has an actual bug, not a planned vuln: `image_path` gets written into the `posts` row as `uploads/{file.filename}`, but `file.save(...)` never gets called anywhere, the file object from `request.files.get("file")` is read for its filename and then dropped. the comment even says "Save the uploaded file to a desired location" as a TODO that never got done. right now `/see` will render `<img src="uploads/whatever.jpg">` pointing at a file that doesn't exist on disk. worth fixing before phase 6's upload vuln work actually needs a working upload path to attack.

separately: `title` and `content` go into that same f-string unescaped too, so `/upload` is injectable on top of the missing file save, two issues stacked in one route.

```python
@app.route("/see")
def see():
    cursor.execute("SELECT * FROM posts")
    posts = cursor.fetchall()
    for post in posts:
        post["username"] = get_username_by_id(post["user_id"])
```

no auth check gate on the sql itself, but the template does check `session.get('username')` before rendering the list, so this one's access-controlled at the view layer, not the route. consistent with how `index.html` and `upload.html` handle it too, gate the html, not the route, the data's always fetched either way.

## templates, quick pass

all five follow the same shape: check `session.get('username')` in jinja, branch the html accordingly. `see.html` renders `post.content` directly with no escaping call, flask's jinja autoescapes by default so this is actually safe as-is for xss, worth remembering for later phases, that protection is automatic, not something this code explicitly did.

`users.html` is the one that matters most right now, it just loops and prints `user.password` straight into a `<li>`, no login check at all in the template or the route. anyone hitting `/users` cold gets the full credential list.

## current attack surface, end of phase 1

| route | vuln | type |
|---|---|---|
| `/login` | `' OR '1'='1' --` bypasses auth entirely | sqli, auth bypass |
| `/register` | username insertable via raw f-string | sqli |
| `/delete` | password field reuses the same vulnerable query | sqli, possible auth bypass |
| `/users` | full plaintext password list, no auth gate | broken access control |
| `/upload` | title/content injectable, file never actually saved | sqli + separate functional bug |
| `/see` | `get_username_by_id` per-post lookup injectable | sqli (less direct, user_id is int-ish but still f-string) |

## next session

fix the upload bug first, `file.save()` is missing entirely, `/see` can't display real images until that's in. then phase 1 testing proper: confirm the `' OR '1'='1' --` bypass against `/login`, try it against `/delete`'s password field too since that route shares the same vulnerable function. after that, phase 2 per the original plan.