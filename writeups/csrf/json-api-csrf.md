# json api csrf: tracing the current application's boundary

## the important project fact

This version of vulnboard does not expose a JSON API. Its state changing routes are HTML form routes:

```python
@app.route("/upload", methods=["GET", "POST"])
def upload():
    ...
    title = request.form.get("title")
    content = request.form.get("content")
```

The application reads `request.form`, not `request.get_json()`. That means the common JSON payload below is not accepted by the current `/upload` route.

This distinction matters. A JSON CSRF example must be based on an endpoint that parses JSON and performs a state changing action. The current project has no such endpoint, so the correct trace is a rejected request rather than a claimed exploit.

## attempted JSON request

An attacker might try to send this request from a malicious page:

```javascript
fetch("http://127.0.0.1:5000/upload", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    title: "json csrf test",
    content: "this should not reach the current form parser"
  })
});
```

The intended HTTP request would look like this:

```http
POST /upload HTTP/1.1
Host: 127.0.0.1:5000
Content-Type: application/json
Cookie: session=<victim's signed flask session cookie>

{"title":"json csrf test","content":"this should not reach the current form parser"}
```

## what happens underneath the hood

There are two browser level cases.

### cross origin request

For a real cross origin browser request, `Content-Type: application/json` is not a simple form content type. The browser normally sends a CORS preflight first:

```http
OPTIONS /upload HTTP/1.1
Origin: https://attacker.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

The current Flask application has no CORS handler for this API flow. The browser therefore does not allow the attacker page to complete the JSON request. `credentials: "include"` does not bypass CORS. It only asks the browser to include cookies if the request is permitted.

### request sent without browser CORS enforcement

A direct command line request can still show what the Flask route does with the JSON body:

```bash
curl -i -b victim.cookies -X POST http://127.0.0.1:5000/upload \
  -H 'Content-Type: application/json' \
  -d '{"title":"json csrf test","content":"json body"}'
```

Flask does not place these JSON fields in `request.form`. The route evaluates:

```python
request.form.get("title")   # None
request.form.get("content") # None
```

The first validation condition succeeds because both values are missing:

```python
if not content or not title:
    return "Content and title are required.", 400
```

The response is:

```http
HTTP/1.1 400 BAD REQUEST
Content-Type: text/html; charset=utf-8

Content and title are required.
```

No `INSERT` is constructed, and no `db.commit()` runs. The JSON body therefore does not create a post in the current application.

## why this is not currently a JSON CSRF exploit

The current route has two separate boundaries:

1. It expects browser form fields through `request.form`.
2. It does not expose an endpoint that calls `request.get_json()` and changes state.

The missing CSRF token is still a vulnerability for the form based `/upload` example documented in `post-based-csrf.md`. It does not automatically make every JSON request exploitable.

A JSON CSRF vulnerability would exist only after adding a route shaped like this:

```python
@app.route("/api/profile", methods=["POST"])
def update_profile():
    data = request.get_json()
    email = data["email"]
    # update the database and commit
```

If that route also accepted credentialed cross origin requests because of permissive CORS, the trace would be:

```text
attacker page -> browser sends victim cookie -> Flask parses JSON
-> route updates database -> commit -> victim's account changes
```

That hypothetical route is not part of the current code and should not be presented as a verified vulnboard result.

## verification checklist

| check | result |
|---|---|
| current app has a JSON API route | no |
| `/upload` calls `request.get_json()` | no |
| JSON fields populate `request.form` | no |
| JSON sent to `/upload` reaches the SQL `INSERT` | no |
| current `/upload` JSON request returns `400` | yes, because title and content are missing from `request.form` |
| a future credentialed JSON endpoint could be CSRF vulnerable | yes, if CORS and request handling allow it |
