# vulnboard — software design document

resolved decisions from the discovery interview, carried through every phase below:

| decision | resolution |
|---|---|
| backend | flask (python) |
| database | mysql |
| session/auth | flask's built in signed cookie session, no flask-login, no server side session table |
| file storage | uploads saved to a non web servable folder; the vuln lives in how the admin preview feature processes the file, not in where it's stored |
| rce mechanism | unsafe `pickle.load()` on the uploaded file at preview time |
| testing strategy | manual only. no pytest, no ci. each phase's verification is a command or payload you run yourself and capture for the writeup |
| hosting | docker compose, local only, never exposed on a public ip/port |

---

## phase 0: setup & scaffolding

### 1. concept table

| phenomenon | brief explanation | how it's used in this phase |
|---|---|---|
| docker compose multi-container app | one `docker-compose.yml` defines and networks several containers (web, db) that would otherwise need manual setup each | runs flask and mysql as two services on one internal network, so the app never touches the host network directly |
| flask app factory pattern | a `create_app()` function builds and returns the flask app instead of a module level global | keeps config swappable later and is the conventional flask project shape |
| `.env` for secrets | environment variables loaded from a file instead of hardcoded in source | holds the db password and flask secret key; also doubles as this phase's sensitive data exposure vuln, since it's placed somewhere reachable |

### 2. resources & libraries

| library/tool | why it's needed |
|---|---|
| `flask` | the web framework |
| `python-dotenv` | loads `.env` into the app config at startup |
| `mysql-connector-python` | talks to mysql from flask without an orm, keeps queries visible for the sqli phase later |
| `docker`, `docker compose` | runs the whole stack locally without installing mysql/python on the host |

### 3. file & folder structure

```
vulnboard/
├── docker-compose.yml       # new — defines web + db services
├── Dockerfile                # new — builds the flask image
├── .env.example               # new — template for secrets, committed
├── .env                        # new — real secrets, gitignored, but readable from inside the running container (intentional exposure)
├── app/
│   ├── __init__.py            # new — create_app() factory, DEBUG=True
│   ├── config.py               # new — loads .env values
│   └── db.py                    # new — raw mysql connection helper
└── requirements.txt           # new
```

### 4. plan

- write `docker-compose.yml` with a `web` service (builds from local `Dockerfile`) and a `db` service (official `mysql` image), both on one internal network, `web` port 5000 bound to `127.0.0.1` only
- write the flask app factory with `DEBUG=True` (intentional, feeds the sensitive data exposure vuln via verbose stack traces)
- load `FLASK_SECRET_KEY` and mysql credentials from `.env` via `python-dotenv`
- place `.env` such that it's reachable by path once debug mode leaks a stack trace with the project's file paths (don't serve it directly through a static route, let debug mode do the leaking, that's the actual vuln)
- confirm the db container initializes with an empty schema (tables come in phase 1)

### 5. verification criteria

**milestone:** `docker compose up` brings up flask and mysql, flask responds on `127.0.0.1:5000`, and the app is unreachable from outside the host.

| # | behavior | type |
|---|---|---|
| 1 | `docker compose up` starts both containers and flask serves a response on `127.0.0.1:5000` | should |
| 2 | triggering an unhandled exception in the app returns a werkzeug debug traceback exposing file paths and config | should |
| 3 | the app should not be reachable from another machine on the network, only from the docker host itself | should not |
| 4 | `.env` should not be committed to git (confirm `.env` is in `.gitignore`, only `.env.example` is tracked) | should not |

**test list:**
```
[manual] docker compose up --build, curl http://127.0.0.1:5000        (row 1)
[manual] hit a route with a forced exception, confirm traceback shown  (row 2)
[manual] curl http://<host-lan-ip>:5000 from another device, confirm it fails  (row 3)
[manual] git ls-files | grep .env, confirm only .env.example appears   (row 4)
```

---

## phase 1: auth & sql injection surface

### 1. concept table

| phenomenon | brief explanation | how it's used in this phase |
|---|---|---|
| string concatenated sql | building a query by pasting user input directly into the query string instead of using placeholders | the login query is built this way on purpose, it's the sqli vuln |
| flask session cookie | flask signs a cookie with the secret key to track "logged in" state, no server side session store | set after a successful login, read by `login_required` checks later |
| plaintext password storage | storing passwords as-is in the db instead of hashed | intentional, this is the other half of the sensitive data exposure vuln alongside the leaky `.env` |

### 2. resources & libraries

no new libraries, built on what phase 0 installed.

### 3. file & folder structure

```
app/
├── routes/
│   └── auth.py              # new — /register, /login, /logout
├── models/
│   └── user.py                # new — raw sql helpers for the users table
└── templates/
    ├── register.html          # new
    └── login.html               # new
```

### 4. plan

- create the `users` table (id, username, password plaintext, is_admin boolean) on first app start
- build `/register`: inserts username/password as-is, no hashing
- build `/login`: query is string concatenated, e.g. `f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"`
- on successful login, set `session['user_id']` and `session['is_admin']`
- seed one admin account at startup with a weak, documented default password
- build `/logout`: clears the session

### 5. verification criteria

**milestone:** a user can register and log in normally, and a crafted username bypasses the password check entirely via sql injection.

| # | behavior | type |
|---|---|---|
| 1 | a normal username/password pair logs in and sets a valid session | should |
| 2 | a username of `' OR '1'='1' -- ` with any password logs in as the first user in the table without knowing a real password | should |
| 3 | the login query should not use parameterized placeholders (this is deliberate, confirming the vuln is actually present) | should not |
| 4 | passwords should not be hashed in the `users` table (deliberate, confirms sensitive data exposure is demonstrable) | should not |

**test list:**
```
[manual] register a user, log in with correct creds, confirm session cookie set         (row 1)
[manual] POST /login with username=' OR '1'='1' -- , any password, confirm logged in     (row 2)
[manual] read app/routes/auth.py, confirm the query is an f-string, not a placeholder     (row 3)
[manual] query the users table directly, confirm password column is plaintext             (row 4)
```

---

## phase 2: guestbook & stored xss / html injection

### 1. concept table

| phenomenon | brief explanation | how it's used in this phase |
|---|---|---|
| jinja2 autoescaping | by default jinja2 escapes `<`, `>`, `&` etc. so user content can't inject html/js into the page | deliberately bypassed with the `| safe` filter on the post content field, that's the vuln |
| stored xss | a malicious script saved to the database and executed every time another user views the page, as opposed to reflected xss which needs a crafted link | the payload lives in a guestbook post, fires on anyone who views the guestbook, including the admin account used in the csrf phase |

### 2. resources & libraries

no new libraries.

### 3. file & folder structure

```
app/
├── routes/
│   └── guestbook.py         # new — / (list + create post)
├── models/
│   └── post.py                # new — raw sql helpers for the posts table
└── templates/
    └── guestbook.html         # new — renders post.content with | safe
```

### 4. plan

- create the `posts` table (id, user_id, content, created_at)
- build `/` (guestbook): GET renders all posts, POST inserts a new one, content stored exactly as submitted
- render each post's content with `{{ post.content | safe }}` in the template, disabling autoescape for that field specifically
- require login to post (reuses phase 1's session check)

### 5. verification criteria

**milestone:** a post containing a `<script>` tag executes in the browser of anyone who views the guestbook afterward, not just the poster.

| # | behavior | type |
|---|---|---|
| 1 | a post containing plain html (e.g. `<b>bold</b>`) renders as formatted html, not escaped text | should |
| 2 | a post containing `<script>alert(document.cookie)</script>` executes when any user, including a separately logged in account, views the guestbook | should |
| 3 | the guestbook template should not escape the post content field (confirms `| safe` is actually in use) | should not |

**test list:**
```
[manual] post "<b>bold</b>", view guestbook, confirm it renders bold, not literal tags   (row 1)
[manual] post the script payload, log in as a second account, view guestbook, confirm alert fires  (row 2)
[manual] read templates/guestbook.html, confirm | safe is present on post.content        (row 3)
```

---

## phase 3: csrf on post deletion

### 1. concept table

| phenomenon | brief explanation | how it's used in this phase |
|---|---|---|
| csrf (cross site request forgery) | a request that changes state (like deleting data) gets triggered by the victim's browser without their intent, because the browser auto-sends their session cookie to any request, even one the victim didn't knowingly make | the delete endpoint trusts the session cookie alone, no token proving the request came from vulnboard's own page |
| state-changing GET request | using GET for an action that modifies data, instead of POST | makes the csrf trivial to demonstrate: a single `<img src="...">` tag can trigger it, no form or js needed |

### 2. resources & libraries

no new libraries (no flask-wtf, csrf protection is intentionally absent).

### 3. file & folder structure

```
app/
└── routes/
    └── guestbook.py          # modified — adds /post/delete/<id>
```

### 4. plan

- add `/post/delete/<id>` as a GET route, no csrf token, checks only that `session['user_id']` is set (doesn't even check the post belongs to that user, that's part of the point)
- this is the natural payoff for phase 2's stored xss: craft a post whose script tag auto-navigates the victim's browser to the delete url
- no ui change needed beyond a delete link on your own posts

### 5. verification criteria

**milestone:** a logged in victim who simply views a crafted guestbook post has one of their posts deleted without clicking anything themselves.

| # | behavior | type |
|---|---|---|
| 1 | visiting `/post/delete/<id>` while logged in deletes that post immediately | should |
| 2 | an `<img src="/post/delete/3">` payload stored via phase 2's xss triggers the deletion automatically when a logged in victim views the page | should |
| 3 | the delete route should not require any token or confirmation beyond an active session | should not |

**test list:**
```
[manual] while logged in, visit /post/delete/<id> directly, confirm the post is gone   (row 1)
[manual] post <img src="/post/delete/3"> as a guestbook entry, log in as another user, view guestbook, confirm post 3 is deleted  (row 2)
[manual] read app/routes/guestbook.py, confirm no token check on the delete route       (row 3)
```

---

## phase 4: malicious file upload

### 1. concept table

| phenomenon | brief explanation | how it's used in this phase |
|---|---|---|
| extension/content-type trust | deciding a file is "safe" based on its filename extension or the `Content-Type` header the browser sends, both of which the uploader fully controls | the upload route accepts anything, there's no allowlist, no magic byte check |
| non web servable storage | saving uploads outside the `static/` folder so they can't be fetched directly by url | keeps this phase's vuln purely about acceptance, not accidental direct execution via url, that's deliberately saved for phase 5 |

### 2. resources & libraries

| library/tool | why it's needed |
|---|---|
| `werkzeug.utils.secure_filename` | used loosely here (or skipped) since the point is the upload accepts arbitrary file types, not that the filename itself is unsafe |

### 3. file & folder structure

```
app/
├── routes/
│   └── upload.py             # new — /upload
├── models/
│   └── upload.py               # new — raw sql helpers for the uploads table
├── uploads/                     # new — gitignored, not under app/static
└── templates/
    └── upload.html               # new
```

### 4. plan

- create the `uploads` table (id, user_id, filename, filepath, created_at)
- build `/upload`: accepts any file, any extension, any size, saves it to `app/uploads/` with the original filename
- insert a row recording who uploaded what and where
- no file type validation, no size limit, no content inspection at this phase, that arrives (and gets exploited) in phase 5

### 5. verification criteria

**milestone:** any file, including a `.pkl` disguised with a `.jpg` extension, uploads successfully and is recorded in the database.

| # | behavior | type |
|---|---|---|
| 1 | uploading a normal image file succeeds and appears in the uploads table | should |
| 2 | uploading a file with a `.jpg` extension whose actual content is an arbitrary binary (e.g. a pickle payload) is accepted without complaint | should |
| 3 | the upload route should not check file extension, mime type, or magic bytes | should not |

**test list:**
```
[manual] upload a real .jpg, confirm it saves and appears in the uploads table      (row 1)
[manual] rename a .pkl file to evil.jpg, upload it, confirm it's accepted            (row 2)
[manual] read app/routes/upload.py, confirm no validation logic exists               (row 3)
```

---

## phase 5: admin preview & remote code execution

### 1. concept table

| phenomenon | brief explanation | how it's used in this phase |
|---|---|---|
| unsafe deserialization | loading a serialized object (like a python pickle) and trusting its contents, when pickle format allows arbitrary code to run during loading itself, not just after | the admin "preview" feature calls `pickle.load()` directly on the uploaded file's bytes |
| `__reduce__` exploitation | a pickle-specific technique: defining a class whose `__reduce__` method returns a callable (like `os.system`) and its arguments, which pickle will call during deserialization | this is the actual exploit payload you'll write to get code execution |
| privilege boundary | the preview feature is only reachable by the seeded admin account from phase 1 | frames the chain realistically: attacker uploads the payload as a normal user, waits for (or in your demo, simulates) an admin previewing it |

### 2. resources & libraries

no new libraries, `pickle` is python's standard library.

### 3. file & folder structure

```
app/
└── routes/
    └── admin.py             # new — /admin/preview/<upload_id>, admin only
```

### 4. plan

- build `/admin/preview/<upload_id>`, gated on `session['is_admin']`
- the route reads the file from `app/uploads/` by the path stored in phase 4's table and calls `pickle.load()` on its contents, intended to "preview metadata" but actually executing anything the pickle defines
- write the payload: a small python script that builds a malicious pickle with `__reduce__` returning `(os.system, ("id > /tmp/pwned",))` or a reverse shell one liner
- document the full chain: register as normal user → upload the crafted pickle disguised as an image → log in as admin (seeded weak creds from phase 1) → hit the preview route → command executes

### 5. verification criteria

**milestone:** the crafted pickle uploaded in phase 4 executes an arbitrary shell command on the server the moment the admin preview route processes it.

| # | behavior | type |
|---|---|---|
| 1 | visiting `/admin/preview/<upload_id>` on a normal image does nothing unexpected | should |
| 2 | visiting `/admin/preview/<upload_id>` on the crafted pickle executes the embedded command (confirm via a file written to disk, or a reverse shell connecting back) | should |
| 3 | a non admin session should not be able to reach the preview route at all | should not |

**test list:**
```
[manual] preview a normal uploaded image, confirm no side effects                      (row 1)
[manual] build the malicious pickle, upload it, log in as admin, hit preview route, confirm /tmp/pwned exists or shell connects back  (row 2)
[manual] hit /admin/preview/<id> while logged in as a non admin user, confirm it's refused  (row 3)
```

---

## phase 6: writeups & final verification pass

### 1. concept table

| phenomenon | brief explanation | how it's used in this phase |
|---|---|---|
| vulnerability chaining | presenting several individually small bugs as one connected attacker path, which is usually more convincing in a writeup than seven isolated bugs | the readme and writeups present phases 1 through 5 as one narrative: recon → auth bypass or account creation → stored xss → csrf → upload → rce |

### 2. resources & libraries

none, this phase is documentation only.

### 3. file & folder structure

```
writeups/
├── 01-sensitive-data-exposure.md   # new
├── 02-html-injection.md              # new
├── 03-stored-xss.md                    # new
├── 04-csrf.md                            # new
├── 05-sql-injection.md                     # new
├── 06-file-upload.md                         # new
└── 07-rce.md                                    # new
```

### 4. plan

- write one markdown file per vulnerability: vulnerable code snippet, exact payload used, screenshot or terminal output proving it worked, one paragraph on why it works and what the real fix would be (described, not implemented, per the brief's scope)
- update the root `README.md` vulnerability table to link each row to its finished writeup
- do a full clean run: `docker compose down -v && docker compose up --build`, then reproduce all 7 exploits start to finish on the fresh instance, to confirm nothing in the writeups depends on leftover state from earlier testing

### 5. verification criteria

**milestone:** a fresh `docker compose up` followed by reproducing every payload in the writeups, in order, succeeds end to end with no steps skipped or state assumed.

| # | behavior | type |
|---|---|---|
| 1 | all 7 writeup files exist and each contains a payload, evidence, and an explanation | should |
| 2 | every payload in the writeups reproduces successfully on a freshly built container, not just the one you developed against | should |
| 3 | the readme's vulnerability table links should not point to missing files | should not |

**test list:**
```
[manual] ls writeups/, confirm all 7 files exist and are non empty                         (row 1)
[manual] docker compose down -v && docker compose up --build, replay every payload in order  (row 2)
[manual] click every link in the readme's vulnerability table, confirm none 404              (row 3)
```
