# phase 2: stored xss, csrf, and finally closing out phase 1's debt

screw the strict sdd order, this session did phase 2 (stored xss) and phase 3 (csrf) back to back, plus went back and actually reproduced the sql injection bypass that phase 1 left as "reproduction still outstanding." that's three sdd phases worth of ground in one sitting, documented here as one phase since that's actually how the work happened.

## see.html, the one line that turns on stored xss

before (phase 1, autoescaping still on):

```html
<p>{{ post.content }}</p>
```

after:

```html
<h3>{{ post.title | safe}}</h3>
<p>{{ post.content | safe }}</p>
```

jinja escapes `<`, `>`, `&` by default, so a post containing `<script>` used to render as literal text, not code. `| safe` tells jinja "trust this string, print it raw." that's the entire vuln, one filter, two fields now (title got it too, wasn't planned but content and title go through the same upload form so it was a five second change to leave title consistent).

worth flagging: `image_path` also got the `safe` treatment:

```html
{% if post.image_path %}
![Post Image]({{ post.image_path | safe }})
{# left here with the safe thingie for security and prevention of xss attacks, but that opens up the possibility of other security vulnerabilities, such as csrf #}
{% endif %}
```

that comment in the template is doing real work, worth spelling out why: `image_path` is a url, not free text, so marking it safe doesn't let someone inject a `<script>` tag through it the way `content` does. but a url is still attacker controllable since it's stored unescaped from the upload form, and a url can point at any route on the app, including a state changing one. that's the setup for the csrf chapter below: an `img src` doesn't have to point at a real image.

## /deletepost/<id>, the new route and the actual csrf

```python
@app.route("/deletepost/<int:post_id>")
def delete_post(post_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM posts WHERE id = {post_id}")
    post = cursor.fetchone()
    if post is None:
        return "Post not found.", 404
    if post.get("user_id") != session.get("user_id"):
        return "You are not authorized to delete this post.", 403
    cursor.execute(f"DELETE FROM posts WHERE id = {post_id}")
    db.commit()
    return "Post deleted successfully!"
```

two things stacked here, same way `/upload` had two issues in one route back in phase 1:

- it's a `GET` route that deletes a row. a `GET` is supposed to be side effect free, that's the whole point of the http verb, browsers and crawlers assume they can fire `GET` requests without asking. an `<img src="/deletepost/3">` is a `GET` request, no click needed, no form submission, just the browser trying to load an image.
- the ownership check (`post.user_id != session.user_id`) is real, it does stop a random logged in user from deleting someone else's post directly. but it answers "does this session own the post", not "did this person mean to delete it." csrf lives exactly in that gap: the victim's browser sends the victim's real session cookie automatically, so the check passes, the attacker never needed to know the victim's password or forge anything.

chain this with the `image_path | safe` change above: a malicious post doesn't need a `<script>` tag to cause damage anymore, `<img src="/deletepost/3">` stored as the image path field (or even just in `content`, same safe treatment there) is enough. victim opens `/see`, browser tries to load the "image", `/deletepost/3` fires with the victim's cookie, post's gone. no alert box, no console, nothing visible.

added the matching link in `see.html`:

```html
<a href="/deletepost/{{ post.id }}">Delete post</a>
```

plain href, no token, no confirmation step. that's on purpose per the vuln boundary in `AGENTS.md`, not an oversight.

## the delete_account() change i need to actually decide on

found this diffing against phase 1's `auth.py`:

```python
# phase 1
password = request.form.get("password")

# now
password = request.args.get("password")
```

`request.args` reads the query string (`?password=...`), `request.form` reads the posted form body. `delete.html`'s form is still:

```html
<form method="POST" action="/delete">
    <input type="password" id="password" name="password" required>
    <button type="submit">delete</button>
</form>
```

that's a `POST` with the password in the body, same as always. if `delete_account()` is now reading `request.args` instead, the actual delete page on the site is broken: every real submission through the form will hit `if not password:` and bounce with "Password is required," because the password never shows up in the query string at all.

not sure yet if this was an intentional pivot (maybe toward testing the sqli bypass against `/delete` via a crafted url, which is easier to demo as a one line curl against `?password=...` than a form post) or just a slip while testing something else and never reverted. either way it needs a decision next session: either put it back to `request.form.get`, or update `delete.html` to match if the query string version is deliberate. leaving it as is means the delete flow is currently just broken for a normal user clicking through the ui.

## writeups, the actual deliverable this session

this is where most of the session actually went. five new writeups, one old one upgraded from theory to evidence:

| writeup | status | what it covers |
|---|---|---|
| `writeups/xss/stored-xss.md` | done, payloads and html traces written, alert(1) execution not yet captured from a real browser | the `/upload` → `posts.content` → `/see` chain, `<b>bold</b>` as the escaping proof, `<img src=x onerror=alert(1)>` as the execution proof |
| `writeups/xss/link-based(reflected).md` | done, comparative only | explains reflected xss as a concept, explicitly notes vulnboard doesn't have a reflected route right now, contrasts it against the stored one above |
| `writeups/xss/dom.md` | done, comparative only | same deal for dom based xss, `innerHTML` vs `textContent`, also explicitly not present in vulnboard yet |
| `writeups/csrf/csrf.md` | done, has example curl and "expected" output, no pasted real terminal evidence yet | the `/deletepost/<id>` get based csrf, including the stored `<img src="/deletepost/10">` auto fire chain |
| `writeups/csrf/post-based-csrf.md` | done, example request/response written, not captured from a live run | `/upload` accepting a cross site form post since there's no csrf token |
| `writeups/csrf/json-api-csrf.md` | done | honestly more of a "why this doesn't apply yet" note, vulnboard has no json api route so this documents the boundary rather than an exploit |
| `writeups/sql_injections/sql_injections.md` | **done, real evidence**, closes phase 1's open todo | actual curl runs against the running container, real 302 redirects, real session cookies in the response headers for both the `' OR '1'='1'` style bypass and the `'--` comment bypass |

the sqli one is the one worth being proud of, it's the only writeup in the list with genuine captured output instead of "expected result". the other five are mechanism-correct but still owe a real terminal capture, that's explicit debt, not an oversight i'm hiding from myself.

## writeups also moved folders, and the readme doesn't know yet

writeups used to be flat (`writeups/01-sensitive-data-exposure.md` style, matching the readme's vulnerability table). they're now grouped by vuln class instead: `writeups/xss/`, `writeups/csrf/`, `writeups/sql_injections/`, `writeups/file upload/`. makes sense as the xss and csrf writeups multiplied into several files each, flat numbering stops scaling the moment one vuln class needs more than one file.

but `README.md`'s table still links to the old flat paths:

```md
| 3 | stored xss | guestbook post rendering | [writeup](writeups/03-stored-xss.md) |
```

that file doesn't exist anymore, it's `writeups/xss/stored-xss.md` now. every row in that table is stale. this stacks on top of the `app/` vs `logic/` diagram mismatch that's been sitting in the loose ends list since `before_phase2.md` and still hasn't been touched.

also, mildly annoying: `writeups/file upload/` has a literal space in the folder name, every other folder uses a hyphen (`writeups/sql_injections/` uses an underscore even, so it's not even consistent with itself). a space in a path means every future `cd` or script path needs quoting. worth renaming to `file-upload` for consistency while fixing the readme links anyway, free cleanup riding along with a change i have to make regardless.

## current attack surface, updated

| route | vuln | type | evidence status |
|---|---|---|---|
| `/login` | `' OR '1'='1' --` / `' --` auth bypass | sqli, auth bypass | **captured**, real curl output in `sql_injections.md` |
| `/delete` | reuses the vulnerable credentials query, also currently broken for normal use (see above) | sqli, possible auth bypass, functional bug | untested this session, blocked on the `request.args` decision |
| `/users` | plaintext password dump, no auth gate | broken access control | unchanged from phase 1, still untouched |
| `/upload` | title/content/image_path injectable, no csrf token | sqli + csrf | csrf side documented in `post-based-csrf.md`, no captured run |
| `/see` | renders `post.content`, `post.title`, `post.image_path` with `\| safe` | stored xss / html injection | documented, alert(1) execution not captured yet |
| `/deletepost/<id>` | state changing `GET`, ownership check only, no token | csrf | documented, no captured run, chains directly off the stored xss above |

## loose ends to carry into next session

| what | where | why it matters |
|---|---|---|
| `delete_account()` reads `request.args` but `delete.html` posts a form body | `logic/auth.py` / `templates/delete.html` | account deletion is currently broken for a normal click through user, needs a decision then a fix |
| readme vulnerability table links to flat writeup paths that no longer exist | `README.md` | every link in that table currently 404s |
| `writeups/file upload/` has a space in the folder name | `writeups/` | inconsistent with the other folders, fix while touching the readme anyway |
| readme repo structure diagram still shows `app/`, real package is `logic/` | `README.md` | flagged back in `before_phase2.md`, still not done, two sessions old now |
| stored xss `alert(1)` never captured from an actual browser run | `writeups/xss/stored-xss.md` | writeup is mechanism correct but has no real evidence attached |
| csrf writeups (`csrf.md`, `post-based-csrf.md`) have no captured terminal output | `writeups/csrf/` | same gap as above, "expected response" isn't proof |
| `/deletepost/<id>` only tested by reading the code, not by actually hitting it | n/a | need the owner case, the 403 case, and the stored-img auto fire case all run for real |
| `logic/__pycache__/` still showing up in context dumps | `.gitignore` | flagged last session too, confirm it's actually ignored, not just assumed |
| `AGENTS.md`'s old `## Gotchas` section is gone, these two tables have been standing in for it across two sessions now | `AGENTS.md` | worth deciding if gotchas live back in `AGENTS.md` or just stay here in the phase notes going forward |

## next session

decided not to chase the loose ends table above next, not yet. going straight for the capstone instead: phase 5 (admin preview rce) then phase 6 (writeups and final pass). the loose ends aren't gone, they're just parked, this project's whole point is the full chain ending in a shell, and that's the piece still missing.

**phase 5 → admin preview rce**

1. build `/admin/preview/<upload_id>`, gated on `session['is_admin']`
2. route calls `pickle.load()` directly on the stored file's bytes
3. write exploit script: pickle with `__reduce__` returning `(os.system, ("id > /tmp/pwned",))`
4. full chain test: register → upload pickle as `evil.jpg` → log in as admin → hit preview → confirm command ran
5. test a normal image through preview, confirm no side effects
6. confirm a non admin session can't reach the route
7. write `writeups/07-rce.md`

**phase 6 → writeups and final pass**

1. confirm all 7 writeup files exist, non empty, each with snippet, payload, evidence, and why
2. update `README.md` vuln table, link every row to its writeup
3. `docker compose down -v && docker compose up --build`
4. replay all 7 exploits on the fresh container, start to finish
5. click every readme link, confirm none 404
