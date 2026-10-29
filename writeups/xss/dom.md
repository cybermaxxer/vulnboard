# dom based xss: client side data reaching an html sink

## what the bug is

dom based xss happens entirely in the browser. the server response can be unchanged while client side JavaScript reads attacker controlled data and places it into an unsafe DOM sink such as `innerHTML`, `document.write`, or an unsafe attribute assignment.

the vulnerable pattern is:

```javascript
const name = new URLSearchParams(window.location.search).get("name");
document.getElementById("welcome").innerHTML = "Hello " + name;
```

the source is `window.location.search`. the sink is `innerHTML`. the browser treats the value as HTML instead of text.

## request and browser trace

the victim opens a URL containing attacker controlled data:

```http
GET /welcome.html?name=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E HTTP/1.1
Host: 127.0.0.1:5000
```

the server can return an ordinary page. after the page loads, JavaScript performs these steps:

```text
window.location.search
  -> URLSearchParams.get("name")
  -> name = <img src=x onerror=alert(1)>
  -> innerHTML = "Hello " + name
  -> browser creates an img element
  -> failed image load dispatches error
  -> alert(1) executes
```

the payload does not need to appear in the raw HTML response. it is introduced after the response has arrived, when the script mutates the DOM.

## safe comparison

using `textContent` keeps the same value as text:

```javascript
const name = new URLSearchParams(window.location.search).get("name");
document.getElementById("welcome").textContent = "Hello " + name;
```

the DOM then contains visible text rather than a new image element. the key difference is not the URL parser; it is the HTML interpreting sink.

## relationship to this project

the current vulnboard stored xss path is server rendered. `/upload` saves the payload, `/see` returns it, and `{{ post.content | safe }}` lets the browser parse it. that is stored xss, not dom based xss.

the browser side mechanism is similar after the sink is reached, but the source and storage path are different:

| type | source | persistence |
|---|---|---|
| stored xss in vulnboard | database value rendered with `safe` | saved in `posts.content` |
| dom based xss | URL, hash, storage, or another client side value | not required |

## verification checklist

| check | result |
|---|---|
| attacker input comes from the URL | yes, `location.search` |
| server must reflect the payload | no |
| JavaScript writes attacker input to `innerHTML` | yes |
| the browser parses the value as HTML | yes |
| replacing `innerHTML` with `textContent` prevents markup parsing | yes |
