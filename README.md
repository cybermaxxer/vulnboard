# vulnboard
a deliberately vulnerable guestbook/blog app, built to practice and document web exploitation after finishing htb academy's **web requests** and **introduction to web applications** modules.

the app chains together every vulnerability class covered in those modules plus malicious file upload and remote code execution, so the full attacker path (find an input → exploit it → get a shell) lives in one small codebase instead of five disconnected scripts.

stack:

- **backend:** flask (python)
- **database:** mysql
- **frontend:** plain html, css, js
- **runtime:** docker compose, local only

---

## setup

```bash
git clone https://github.com/<your-username>/vulnboard.git
cd vulnboard
docker compose up --build
```

app runs at `http://127.0.0.1:5000`. default seeded accounts and db credentials are in `.env.example`, copy it to `.env` before first run.

---

## vulnerabilities covered

each one has its own writeup under `/writeups`, with the vulnerable code, the payload used, and a screenshot or terminal output proving it works.

| # | vulnerability | where it lives | writeup |
|---|---|---|---|
| 1 | sensitive data exposure | debug mode on, `.env` reachable, plaintext passwords | [writeup](writeups/01-sensitive-data-exposure.md) |
| 2 | html injection | guestbook post rendering | [writeup](writeups/02-html-injection.md) |
| 3 | stored xss | guestbook post rendering | [writeup](writeups/03-stored-xss.md) |
| 4 | csrf | "delete my post" action | [writeup](writeups/04-csrf.md) |
| 5 | sql injection | login form | [writeup](writeups/05-sql-injection.md) |
| 6 | malicious file upload | avatar/attachment upload | [writeup](writeups/06-file-upload.md) |
| 7 | remote code execution | admin "preview uploaded file" feature, chained off #6 | [writeup](writeups/07-rce.md) |

this is the exploitation-only version of the app. no fixed/patched branch, by design, this round is about attacking, not hardening.

---

## repo structure

```
vulnboard/
├── app/                # flask application
├── docker-compose.yml
├── .env.example
├── writeups/           # one markdown file per vulnerability
└── README.md
```

---

## why

htb academy's "introduction to web applications" module recommends building a small app and attacking it as the fastest way to turn theory into retained skill. this is that, scoped to a 3 day build.

part of my cjca (junior cybersecurity analyst) learning path. more notes for cjca [here](https://github.com/cybermaxxer/junior_cybersecurity_path_notes-writeups).
