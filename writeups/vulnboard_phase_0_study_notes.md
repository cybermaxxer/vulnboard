# VulnBoard: Phase 0 Study Notes (Setup & Scaffolding)

## 1. Project Overview
**VulnBoard** is an intentionally vulnerable guestbook/blog application built to practice web exploitation (SQL injection, XSS, CSRF, RCE, etc.). 

**Phase 0 Goal:** Set up a secure local environment using Docker so the vulnerable app runs strictly on your computer (`127.0.0.1`) without exposing you to the internet. We also built the foundational database connection and configuration that the rest of the app will use.

---

## 2. Secrets and Version Control

### `.env` and `.env.example`
* **What they are:** Environment variables. Apps need passwords and secret keys, but hardcoding them directly into Python files is dangerous.
* **`.env`:** Holds the actual secret values.
* **`.env.example`:** A dummy version with fake values. You share this one so other developers know what variables the app needs to run.

### `.gitignore`
* **What it does:** Tells Git (the version control system) which files to completely ignore and never upload to a repository.
* **Why we use it:** To ensure we never accidentally upload `.env` (our secrets) or the `app/uploads/` folder (where malicious files will be uploaded during Phase 6).
* **The `.gitkeep` trick:** Git ignores empty folders. To force Git to track the `app/uploads/` folder so it exists for the app to use, we put an empty file named `.gitkeep` inside it.

---

## 3. Dependencies (`requirements.txt`)
This file lists the exact Python packages needed. Docker reads this to install them inside the container.
* `flask==3.0.2`: The core web framework. It handles web traffic, URLs, and rendering HTML.
* `python-dotenv==1.0.1`: A helper library that reads our `.env` file and loads the secrets into the computer's memory.
* `mysql-connector-python==8.3.0`: The "driver" that allows our Python code to talk to the MySQL database.

---

## 4. Python Core Concepts (The "Dunders")

Before diving into the code, you must understand these Python rules:

* **`__init__.py`:** If you put this file inside a folder (like `app/`), Python stops treating it as a normal folder and upgrades it to an official **Python Package**. This allows you to import files from it (e.g., `from app.config import Config`).
* **`__name__`:** An invisible nametag Python assigns to every file. 
  * In `app/config.py`, `__name__` is `"app.config"`.
  * In `app/__init__.py`, `__name__` is just `"app"` (because `__init__.py` represents the whole folder).
* Flask needs `__name__` so it knows exactly where the root of your project lives on your hard drive, allowing it to find your HTML templates and upload folders.

---

## 5. The Application Code (`app/` Directory)

### A. `app/config.py` (Configuration)
```python
import os
from dotenv import load_dotenv

load_dotenv() # Reads the .env file

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "fallback")
    MYSQL_HOST = os.getenv("MYSQL_HOST", "db") 
    MYSQL_USER = os.getenv("MYSQL_USER", "vulnuser")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "vulnpass")
    MYSQL_DB = os.getenv("MYSQL_DATABASE", "vulnboard")
    
    DEBUG = True # Intentional Vulnerability!
```
* **Explanation:** Gathers all settings into one neat `Config` class.
* **Vulnerability Note:** `DEBUG = True` tells Flask to print detailed error tracebacks to the browser when the app crashes. This is a "Sensitive Data Exposure" vulnerability because it leaks internal file paths to attackers.

### B. `app/db.py` (Database Pipeline)
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
* **The `g` object:** Flask creates `g` (short for "global") as a temporary locker for a single web request. `get_db()` opens a connection and stores it in `g.db`. If a user makes 5 database queries in one click, it reuses the same connection.
* **`close_db()`:** Cleans up and closes the connection so the database doesn't crash from too many open pipelines.

### C. `app/__init__.py` (The Factory)
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
* **`create_app()`:** An "Application Factory". It builds the Flask app, loads the config, and registers routes.
* **`teardown_appcontext`:** Tells Flask: "When you finish sending a web page to the user, run `close_db` automatically."
* **`@app.route`:** Links a URL (like `/` or `/debug-test`) to a specific Python function.

---

## 6. Dockerization (Running without local installs)

Docker creates isolated "mini-computers" (containers) so we don't have to install Python or MySQL on our actual host operating system.

### A. `Dockerfile` (Python Setup)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["flask", "--app", "app", "run", "--host=0.0.0.0", "--port=5000"]
```
* **Explanation:** Downloads a blank Linux system, installs Python, installs our requirements, copies our code in, and runs Flask.
* **Caching:** Docker saves each line as a "layer". If you only change Python code (the second `COPY . .`), Docker reuses the `pip install` layer, making rebuilds take less than 1 second. (Also, no inline comments allowed in this file!)

### B. `docker-compose.yml` (The Orchestrator)
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
* **Explanation:** Boots up two containers (`web` and `db`).
* **Security:** `127.0.0.1:5000:5000` is critical. It forces the vulnerable app to only listen to your local computer (localhost). If anyone else on your WiFi network tries to access it, their connection will be rejected.

---

## 7. Execution Trace: What Happens When You Run It?

### Step 1: `docker compose up --build`
1. Docker reads `docker-compose.yml` and sees two services.
2. It pulls the official `mysql:8.0` image, reads your `.env`, and creates a database (`vulnboard`) and a user (`vulnuser` / `vulnpass`).
3. It reads your `Dockerfile`, installs your Python packages, and boots the `web` container.
4. Inside the `web` container, Docker runs `flask run`.

### Step 2: Flask Startup
1. Flask looks at `--app app` and finds `app/__init__.py`.
2. It runs `create_app()`.
3. It reads `.env` variables via `config.py` and stores them in memory.
4. It registers the URLs `/` and `/debug-test` into its internal routing map.
5. It pauses and listens on port 5000.

### Step 3: The Web Request (Visiting `http://127.0.0.1:5000/`)
1. You hit Enter in your browser. The browser sends an HTTP `GET` request.
2. Docker routes the traffic from your PC's port 5000 into the container's port 5000.
3. Flask creates the temporary `g` object for this specific request.
4. Flask checks its map, sees `/` belongs to `index()`, and runs it.
5. `index()` returns the string `"VulnBoard setup complete and running!"`.
6. Flask runs `close_db()` (cleaning up `g`).
7. Flask packages the string into an HTTP Response and sends it to your browser.

---

## 8. Looking Ahead: Phase 1 (Auth & SQL Injection)

**What is Phase 1?**
We will build the user registration and login system, intentionally making it vulnerable to **SQL Injection (SQLi)**.

**What we will build:**
1. **`app/models/user.py`:** Database logic. We will write raw SQL queries using string concatenation (e.g., `f"SELECT * FROM users WHERE username='{username}'"`). This is the root cause of SQLi because it blindly executes user input as code.
2. **`app/routes/auth.py`:** The web routes (`/login`, `/register`). We will set up session cookies to keep users logged in.
3. **HTML Templates:** Basic forms for users to type their usernames and passwords.

**The Attack Plan:**
Because the SQL query doesn't filter out symbols, submitting `' OR '1'='1' --` as a username will manipulate the SQL logic to always equal "True", allowing us to bypass the password check completely and log in as an administrator.