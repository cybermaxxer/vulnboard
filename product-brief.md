# VulnBoard — Product Brief

## 1. Problem & Opportunity
The HTB Academy "Introduction to Web Applications" module teaches web architecture and a first pass at common vulnerabilities (sensitive data exposure, HTML injection, XSS, CSRF, SQLi) entirely through theory and short interactive exercises. The module's own "Next Steps" section recommends building a small web application end to end, connecting it to a database, and then attacking it, as the fastest way to convert that theory into retained, demonstrable skill. There is no ready made project that lets a student build, break, and document a full vulnerability chain (including file upload and RCE, which go beyond the module) in a short, scoped window.

## 2. Target User
A single user: a student on the HTB CJCA (Junior Cybersecurity Analyst) path who already knows Flask, is building a public GitHub portfolio documented with writeups, and wants a project that demonstrates range across the full web vuln list in one coherent app rather than five disconnected toy scripts.

## 3. Core Value Proposition
One small, deliberately vulnerable guestbook/blog app that chains together every vulnerability class the module covered, plus file upload and remote code execution, so a single GitHub repo with one README can show the full attacker path from "found an input" to "got a shell" — a stronger portfolio artifact than isolated snippets.

## 4. Core Loop
Build one vulnerable feature → exploit it manually, capture the payload and evidence → write it up in the README → move to the next feature. Repeated across each vulnerability class until the chain is complete, finishing with the file upload → RCE chain as the capstone.

## 5. Feature Set

| Feature | Priority (MVP / v2 / later) | Why it matters |
|---|---|---|
| User registration & login (plaintext/weak password storage, verbose error messages) | MVP | Carries sensitive data exposure, and is the entry point for SQLi |
| Login form built with raw string-concatenated SQL query | MVP | Classic SQL injection target (auth bypass, data extraction) |
| Guestbook post submission, rendered without sanitization | MVP | Stored HTML injection / stored XSS target |
| "Delete my post" action with no CSRF token | MVP | CSRF target, pairs naturally with the XSS (session riding) |
| Avatar/attachment upload with no file type or content validation | MVP | Malicious file upload target |
| Admin "preview uploaded file" feature that executes/interprets the uploaded file server side | MVP | Turns the file upload into remote code execution, the capstone exploit |
| Debug mode left on, `.env` or config file reachable, secrets in plaintext | MVP | Rounds out sensitive data exposure beyond just passwords |
| MySQL database for users, posts, and uploads metadata | MVP | Matches your stated DB choice, gives SQLi something real to extract |
| Dockerized or scripted one-command local setup | MVP | Keeps the 3 day budget realistic and keeps the app off any public network |
| Fixed/patched version of the app (parameterized queries, escaping, CSRF tokens, upload validation, RCE closed) | later | Explicitly deferred per your answer; exploitation only for this cycle |
| IDOR (reading other users' data by changing an ID) | later | Not in the original module scope or your added list; natural v2 addition if you want it |
| Automated exploit scripts (vs. manual, documented exploitation) | later | 3 day scope is manual exploitation with writeups, not tooling |

## 6. Key User Flows

**Flow A — Stored XSS to session theft to CSRF:**
1. Attacker registers an account, posts a guestbook entry containing a script payload instead of plain text
2. Victim (simulated, e.g. an "admin" account you log in as separately) views the guestbook, payload executes in their session
3. Payload exfiltrates the victim's session cookie or silently submits the unprotected "delete post" request on their behalf
4. You document both the stored XSS and the resulting CSRF as one chained writeup

**Flow B — SQL injection on login:**
1. Attacker submits a crafted username/password pair exploiting the string-concatenated query
2. Query returns true without a valid password, or leaks other rows (usernames, password hashes) via a UNION-based payload
3. You document the vulnerable query, the payload, and the extracted data

**Flow C — Malicious file upload to remote code execution:**
1. Attacker uploads a file disguised as an image but containing executable code (e.g. a Python or PHP reverse shell)
2. The app's "preview" or "process" feature on the admin side opens/executes the uploaded file without validation
3. Attacker gets code execution on the host (reverse shell back to attacker machine, or a webshell they can browse to)
4. You document the upload bypass, the payload, and the shell, with the chain written up as the project's centerpiece

## 7. Platform & Technical Notes
- Backend: Flask (Python), as you specified
- Database: MySQL, as you specified
- Frontend: plain HTML/CSS/JS, kept intentionally simple since the frontend is attack surface, not a design showcase
- Runs locally only, via Docker Compose or a documented local setup script. **Assumption:** the app must never be exposed on a public IP or port; it binds to localhost/docker-internal networking only. This is a flag for you, not a question, since running a deliberately RCE-vulnerable app on the open internet is a real foothold for someone else, not a demo
- No authentication hardening, HTTPS, or production concerns: this is a lab app, not a product

## 8. Explicitly Out of Scope
- The fixed/secure version of the app (patches, mitigations) — exploitation only, for this 3 day cycle
- IDOR and any vulnerability class beyond the module's list plus file upload and RCE
- Automated scanning or exploit tooling (no custom scripts, no sqlmap integration) — manual, documented exploitation
- Any deployment beyond local/Docker; no cloud hosting, no public exposure
- User-facing polish: this is a lab app for one person, not a real guestbook product

## 9. Success Metrics
- All 7 vulnerability classes (sensitive data exposure, HTML injection, XSS, CSRF, SQLi, malicious file upload, RCE) are present in the app and have a working, reproduced exploit
- One README per vulnerability (or one combined README with clear sections) documenting: the vulnerable code, the payload used, a screenshot or terminal output of the exploit succeeding, and a one line explanation of why it works
- The file upload → RCE chain is fully demonstrated end to end (upload, trigger, shell)
- Repo is published on GitHub and ready to link from a LinkedIn post, matching your existing module writeup style

