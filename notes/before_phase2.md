# before phase 2: cleanup session (upload fix, package rename, first writeup)

phase 1 wasn't actually finished, two todos were still hanging off its own notes: `file.save()` was never called, and the `' OR '1'='1' --` bypass was never reproduced or written up. this session closes both. a few things that weren't on the list happened too: the package got renamed from `app` to `logic`, the dockerfile got tighter, and `AGENTS.md` turned into an actual mentor contract instead of just a rules file. phase 2 (stored xss) is next, and it's a small lift given what's already here.

## the missing `file.save()`, finally fixed

phase_1.md flagged this directly: `image_path` was getting written into the `posts` row as `uploads/{file.filename}`, but nothing ever called `file.save(...)`. the file object got read for its filename and dropped. `/see` was rendering `<img>` tags pointing at files that didn't exist.

before:

```python
if file:
    sql_query = f"INSERT INTO posts (title, content, image_path, user_id) VALUES ('{title}', '{content}', 'uploads/{file.filename}', {session['user_id']})"
    cursor.execute(sql_query)
    db.commit()
    cursor.close()
    # Save the uploaded file to a desired location (e.g., 'uploads' folder)
    return f"File '{file.filename}' uploaded successfully!"
```

now:

```python
if file and file.filename:
    filename = file.filename
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    image_path = f"/uploads/{filename}"
    sql_query = f"INSERT INTO posts (title, content, image_path, user_id) VALUES ('{title}', '{content}', '{image_path}', {user_id})"
    cursor.execute(sql_query)
    db.commit()
    cursor.close()
    return f"File '{filename}' uploaded successfully!"
```

three real changes stacked in that one line:

- `if file:` became `if file and file.filename:`. a `FileStorage` object is truthy even when the browser submitted an empty file field, so an upload with no image attached was still falling into the "has image" branch and inserting `image_path = 'uploads/'`. checking `.filename` too is what actually distinguishes "no file chosen" from "a file was chosen."
- `file.save(...)` now runs before the insert. `file.save` is werkzeug's method on the uploaded `FileStorage` object, it streams the upload from memory/temp storage to disk at the path given. that line was always the one actually missing, everything else downstream (the sql insert, the template render) assumed it had already happened.
- `image_path` changed from a relative fragment (`uploads/filename.jpg`) to an absolute url path (`/uploads/filename.jpg`). a relative path resolves against whatever page is currently loaded, `/see`, so it would have pointed at `/uploads/filename.jpg` only by accident depending on the current url. an absolute path always resolves from the domain root, which is what a `<img src="...">` actually needs to hit a real flask route.

that third point only works because of the next change: `UPLOAD_FOLDER` and a route to actually serve from it.

```python
UPLOAD_FOLDER = "/app/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
```

`os.makedirs(..., exist_ok=True)` is the idiomatic way to say "make sure this directory exists, don't error if it already does." without `exist_ok=True`, a second container start would crash on `FileExistsError` the moment the folder was already there from the first run.

```python
@app.route("/uploads/<path:filename>")
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)
```

`<path:filename>` is a flask url converter, `path` specifically (instead of the default `string`) allows slashes through in the captured segment, matters if an uploaded filename ever has a subpath in it. `send_from_directory` is werkzeug's safe version of "serve this file from this folder": it joins the folder and filename, and refuses anything that tries to escape the folder via `../`. that's a real guardrail, not a vuln left in by mistake, path traversal on the file *serve* route wasn't the planned vuln for this phase (that's reserved for the pickle rce chain later), so it's fine to let werkzeug handle it here.

also quietly fixed in the same route: `upload()` previously used `session['user_id']` directly inside the f-string, meaning an unauthenticated POST to `/upload` would throw a `KeyError` straight into `DEBUG=True`'s traceback page, interesting from a sensitive-data-exposure angle, but not the intended vuln for this route. now it's explicit:

```python
user_id = session.get("user_id")
if not user_id:
    return "You must be logged in to upload.", 401
```

## `/see` now orders by `created_at desc`

```python
cursor.execute("SELECT * FROM posts ORDER BY created_at DESC")
```

small change, but worth noting why: without an `ORDER BY`, mysql gives no guarantee at all about row order, it happened to look chronological before because of how innodb was laying out the pages, not because the query asked for it. that's not something to depend on, especially once posts start getting deleted (phase 3) and the table gets fragmented. `created_at` already existed in the schema from phase 1's `init.sql`, so this was free.

## package rename: `app` → `logic`

every `from app.x import` across the codebase became `from logic.x import`, and the dockerfile's entrypoint changed from `flask --app app run` to `flask --app logic run`. functionally identical, flask doesn't care what the package is called as long as `create_app()` or a module-level `app` is reachable from it.

the dockerfile's `COPY` step changed shape at the same time:

before:
```dockerfile
COPY . .
```

after:
```dockerfile
COPY logic ./logic
COPY .env .env
```

`COPY . .` was dragging the entire build context into the image: `notes/`, `development_plans/`, `writeups/`, this very file. none of that needs to exist inside the running container, it's documentation for a human, not code for flask. copying only `logic/` and `.env` keeps the image to what the app actually needs to run, and as a side effect also means editing a note file doesn't bust docker's build cache for the `COPY` layer.

one thing this rename left behind: `README.md`'s repo structure diagram still shows `app/` as the top level folder. that's now wrong, flag it for the next doc pass.

## `AGENTS.md` got a second job

the old `AGENTS.md` was a pure rules file: project, structure, stack, commands, conventions, security, gotchas, what not to do, commit style. useful for an agent executing tasks, not built for an agent teaching while it executes them.

the new version restructures around that gap. `project` stays roughly the same (what vulnboard is, that it's exploitation only). everything after it is new framing:

- `role`: act as an expert socratic coding and security mentor, explain concepts/control flow/syntax/security impact in enough detail to reproduce the result later, guide instead of silently taking over when the task is educational, but make the smallest focused edit and explain afterward when explicitly asked to just implement something.
- `working method`: a numbered loop, read context → state position and immediate task → form one hypothesis with one cheap disconfirming check → make one small reversible change → run the narrowest manual validation → explain cause/effect/evidence → keep steps small, no jumping ahead to later phases.
- `code style`: match existing style, plain flask/raw sql/plain html, no orm or abstraction that would hide the thing being studied, comments explain intent not restate the next line, preserve the lowercase direct writing style in docs.
- `intentional vulnerability boundary`: same list as before (no parameterized queries, no escaping, no csrf tokens, no upload validation, no password hashing, no safe deserialization) but now also says to stop and flag anything that could make the lab reachable from another machine.
- `documentation style`: concept table / resources / structure / plan / verification headings, tables for comparisons, numbered steps for process, writeups explain mechanism not just payload.

this is a direct lift of `code_tutor.md`'s socratic-mentor contract (new this session, see below) folded into the repo's own rules file, so the mentor persona travels with the repo instead of living in a separate prompt someone has to remember to paste.

one thing that didn't survive the rewrite: the old `AGENTS.md` had a `## Gotchas` section reserved for exactly this kind of repo-specific landmine, and it's gone. the `app` → `logic` rename and the stale readme diagram below are the first two candidates for a section like that; whether it comes back or gotchas just live in these phase notes instead is an open question.

## `code_tutor.md` + `context_gatherer.sh`, the actual meta change

these two are new this session and they're the reason this very note exists in the form it does. `context_gatherer.sh` is a small shell script that dumps the whole repo (code, templates, notes, plans) into one text blob for pasting into a fresh llm chat, no manual copy pasting file by file. `code_tutor.md` is the prompt that goes with that dump: it's the same socratic mentor contract that `AGENTS.md`'s `role` and `working method` sections now carry, but written for a one shot "here's my whole project, pick up where I left off" session rather than an agent with persistent repo access.

practically: `AGENTS.md` governs an agent working directly in the repo turn by turn, `code_tutor.md` governs a disposable chat seeded with `context_gatherer.sh`'s dump. two different delivery mechanisms, same teaching contract, kept in sync by hand for now, that's itself a gotcha worth tracking once they drift.

`README.md`'s repo structure diagram got one line added for this (`context_gatherer.sh`, with a comment pointing at `code_tutor.md`), but as noted below the rest of that diagram wasn't updated for the `app` → `logic` rename, so it's half current.

## `writeups/sql_injections.md`, the first real writeup

this is the actual deliverable the phase 1 notes were waiting on: a walkthrough of the `' OR '1'='1' --` style bypass against `get_user_by_credentials()`, written at the "why does a quote character do this" level rather than just "here's the payload." full rewrite of it is in `writeups/sql_injections.md` itself; see the next doc for the cleaned up version.

one gap worth being honest about: the writeup explains the mechanism, but there's no captured terminal output or screenshot in it yet. `sdd.md`'s own phase 1 test list (`[manual] POST /login with username=' OR '1'='1' -- ...`) and `AGENTS.md`'s testing-and-evidence section both expect a real request/response pair, not just the theory. that's the actual remaining phase 1 todo.

## loose ends to carry into phase 2

| what | where | why it matters |
|---|---|---|
| `README.md` repo diagram says `app/`, real folder is `logic/` | `README.md` | first thing a reader hits, currently wrong |
| sqli bypass explained but not reproduced against the running app | `writeups/sql_injections.md` | writeup has no request/response evidence yet |
| `logic/__pycache__/` showed up in this session's context dump | `logic/` | compiled bytecode shouldn't be tracked or dumped, check `.gitignore` covers `__pycache__/` |
| old `AGENTS.md` gotchas section is gone | `AGENTS.md` | the two rows above are exactly what it existed for |

## next session: phase 2, stored xss

per `development_plans/sdd.md`, phase 2 is: posts render html unsafely, specifically `post.content` loses jinja's autoescaping via the `| safe` filter. the schema (`posts` table, `title`/`content`/`image_path`/`created_at`) and the routes (`/upload` to create, `/see` to list) already exist from phase 1, further ahead than the original sdd phase 2 plan assumed, since it pictured a single combined `/` route. not worth restructuring just to match the doc, `/upload` + `/see` already does the same job, so the plan should get updated to match reality instead of the other way around.

the actual work left:

- `see.html` currently renders `{{ post.content }}`, flask's jinja autoescapes by default, so a post containing `<script>` currently shows up as literal escaped text, not executing. that's the safe-by-default behavior phase_1.md's notes already called out.
- change that one line to `{{ post.content | safe }}`. that's the entire vuln, one filter removed on one field.
- test three things: a plain `<b>bold</b>` post renders as formatted html, not literal tags; a `<script>alert(document.cookie)</script>` post executes when a second logged in account views `/see`; `grep`/read `see.html` to confirm `| safe` is actually present (that's `sdd.md`'s three verification rows for this phase).
- writeups: `02-html-injection.md` and `03-stored-xss.md`, same mechanism-first style as the sqli writeup, not just a payload dump.
