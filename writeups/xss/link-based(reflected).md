# reflected xss: request data returned immediately in html

## what the bug is

reflected xss occurs when attacker controlled data arrives in one request and the server copies it into the response without HTML escaping. the payload is not saved in the database. it executes when a victim opens the crafted link or submits the crafted request.

a vulnerable server side example is:

```php
<h2>Search results for: <?php echo $_GET['q']; ?></h2>
```

the application treats `q` as text in the developer's mental model, but `echo` writes the raw value into the response. the browser only sees HTML characters and does not know that they came from a query parameter.

## request to response trace

the attacker creates a link with an encoded payload:

```text
https://example.com/search?q=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E
```

the browser sends:

```http
GET /search?q=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E HTTP/1.1
Host: example.com
```

the server decodes the parameter and produces a response like:

```http
HTTP/1.1 200 OK
Content-Type: text/html

<h2>Search results for: <img src=x onerror=alert(1)></h2>
```

the HTML parser creates the image element. its load fails, the `error` handler runs, and the alert appears. the payload travelled from the URL to the response and then into the browser without being stored.

## safe comparison

the server should escape the value before placing it in HTML. the same input should become:

```html
<h2>Search results for: &lt;img src=x onerror=alert(1)&gt;</h2>
```

the browser displays the characters as text and does not create an image element. a framework template should use its default escaping behavior rather than marking this value safe.

## relationship to vulnboard

vulnboard does not currently have a reflected search route. its `/see` page demonstrates stored xss because the payload is inserted into `posts.content` first and returned on later requests.

the distinction is the lifetime of the input:

| type | request path | stored in database |
|---|---|---|
| reflected xss | crafted request -> immediate response | no |
| stored xss in vulnboard | upload -> database -> later `/see` response | yes |
| dom based xss | browser source -> JavaScript sink | not required |

## verification checklist

| check | result |
|---|---|
| payload is delivered through a link or request | yes |
| server places the decoded value into HTML | yes |
| payload is saved for later viewers | no |
| HTML escaping prevents element creation | yes |
| vulnboard's current `/see` route is reflected xss | no, it is stored xss |
