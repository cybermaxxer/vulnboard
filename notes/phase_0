# phase 0: spin up notes (docker + flask factory)

goal here wasn't to write app logic yet, it was to get a vulnerable flask app booting inside docker, talking to mysql, bound to `127.0.0.1` only, with config pulled from env vars instead of hardcoded. four files do that: `Dockerfile`, `docker-compose.yml`, `app/__init__.py`, `app/config.py`, `app/db.py`.

## Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["flask", "--app", "app", "run", "--host=0.0.0.0", "--port=5000"]
```

`requirements.txt` gets copied and installed before the rest of the code. that's not arbitrary ordering, docker caches each line as a layer. if only app code changes later, docker reuses the cached `pip install` layer instead of re running it, so rebuilds stay fast. flip that order (copy everything, then install) and every code change invalidates the install cache too.

`--host=0.0.0.0` inside the container is fine and necessary, it means "listen on all interfaces inside this container." this isn't what exposes the app to the network; that's controlled entirely by the port mapping in compose, next.

## docker-compose.yml

```yaml
services:
  web:
    build: .
    ports:
      - "127.0.0.1:5000:5000"
    env_file:
      - .env
    depends_on:
      - db

  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "127.0.0.1:3306:3306"
```

`127.0.0.1:5000:5000` is the actual security boundary, not `--host=0.0.0.0`. this binds the host side of the mapping to localhost specifically; anything not originating from the machine itself gets refused at the os level, before it even reaches docker's networking. same thing on the `db` port, so mysql is inspectable locally (for debugging) without being reachable from anywhere else.

`db` as a hostname works because compose runs its own internal dns, service names resolve to whatever internal ip that container currently has, so `MYSQL_HOST=db` in `.env` never breaks even if the container restarts and gets reassigned a different internal ip. no manual ip wiring anywhere.

`depends_on: db` only guarantees the db container starts first, not that mysql is actually ready to accept connections yet, worth remembering if `web` throws connection errors on the very first `docker compose up`.

## app/__init__.py, the factory

```python
from flask import Flask
from app.config import Config
from app.db import close_db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.teardown_appcontext(close_db)

    @app.route("/")
    def index():
        return "VulnBoard setup complete and running!"

    @app.route("/debug-test")
    def debug_test():
        raise RuntimeError("Testing stack trace output in debug mode")

    return app
```

`__init__.py` existing in a folder is what makes python treat that folder as a package. it runs top to bottom the moment anything imports `app`, which is how `create_app` becomes reachable as `from app import create_app`.

`create_app()` is a factory, not a one off setup script. it builds a fresh `Flask` instance, wires in config, teardown, routes, and returns the finished object. the `return app` line matters because `app` is a local variable; without returning it, the whole built instance (routes, config, everything) just gets garbage collected the second the function ends. the flask cli needs that actual object back to call `.run()` on.

`@app.route("/")` registers `index` into flask's internal url map at startup, not at request time. the decorator runs exactly once per route, during this function call, it does not re run on every visit. what runs on every visit is flask looking `/` up in that already built map and calling `index()` directly, since this particular decorator doesn't wrap the function, it just stores a reference to it unchanged.

`debug_test()` deliberately raises an exception, that's not a bug, it exists to prove `DEBUG = True` is actually wired up and shows werkzeug's full traceback/debugger when hit.

## app/config.py

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "default-fallback-key")
    MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
    MYSQL_USER = os.getenv("MYSQL_USER", "vulnuser")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "vulnpass")
    MYSQL_DB = os.getenv("MYSQL_DATABASE", "vulnboard")

    DEBUG = True
```

`load_dotenv()` has to run before the `class Config:` block, not just be written above it, the order matters because a class body executes immediately, line by line, same as any other code. every `os.getenv(...)` call in there is a real function call happening right then, reading whatever is currently sitting in `os.environ`. if `load_dotenv()` hadn't already populated that, every single setting would silently fall back to its hardcoded default, `.env` file present or not.

all of this runs exactly once, at import time, when the container boots. editing `.env` while the server's already running does nothing until a restart re triggers the whole import.

`DEBUG = True` is the planted vuln, hardcoded, not read from env, always on. combined with `/debug-test` above, any unhandled crash on that route hands back werkzeug's interactive debugger: a live python shell in the browser, with access to request context, `SECRET_KEY`, and db creds sitting in the running process. real cve class, not theoretical, this is exactly why debug mode should never ship hardcoded true.

## app/db.py

```python
import mysql.connector
from flask import current_app, g

def get_db():
    if 'db' not in g:
        g.db = mysql.connector.connect(
            host=current_app.config['MYSQL_HOST'],
            user=current_app.config['MYSQL_USER'],
            password=current_app.config['MYSQL_PASSWORD'],
            database=current_app.config['MYSQL_DB']
        )
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
```

`g` is flask's per request scratchpad, created empty at the start of each request, thrown away at the end, never shared across requests or users. `'db' not in g` is checking whether `g.db` has already been set this request; if multiple parts of the code call `get_db()` during the same request, only the first call actually opens a connection, every call after that just returns the one already stored.

`current_app.config['MYSQL_HOST']` instead of importing `Config` directly, since this is a factory app with no single global `app` variable sitting in a file, `current_app` is how any module reaches "whichever app instance is currently running," valid only inside an active request.

`close_db` gets registered via `app.teardown_appcontext(close_db)` back in `__init__.py`, that registration itself is just an append to an internal list flask keeps, happening once at boot. the actual call to `close_db` happens at the end of every single request, guaranteed, even if the route crashed, because flask wraps the route call in a try/except specifically so teardown still fires either way. `g.pop('db', None)` pulls the connection out of `g` and removes it in one step, returning `None` safely if nothing was ever opened, avoids both a `KeyError` from popping a missing key and an `AttributeError` from calling `.close()` on `None`.

## boot sequence, start to finish

1. `docker compose up --build` reads the compose file, builds the `web` image from the dockerfile, pulls `mysql:8.0` for `db`
2. `db` container starts, mysql initializes using the env vars from `.env`
3. `web` container starts, runs `flask --app app run`
4. flask imports the `app` package, `__init__.py` executes, `create_app()` runs
5. inside `create_app()`: `Config` loaded (which already ran `load_dotenv()` plus every `os.getenv()` call when it was imported), both routes registered into the url map, `close_db` registered into the teardown list
6. `return app` hands the built instance back to the cli, server starts listening on `:5000`

from here, every request to `/` or `/debug-test` is just: flask builds a fresh `g`, looks the url up in the already built map, runs the matched function, runs teardown, discards `g`. none of the setup in steps 4 and 5 runs again, that only happens once, at boot.
