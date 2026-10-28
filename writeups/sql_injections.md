# SQL injection archetypes

## The vulnerable query

The login function builds the query with string interpolation:

```python
sql_query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
```

With ordinary input, such as `alice` and `secret`, the database receives:

```sql
SELECT * FROM users
WHERE username = 'alice' AND password = 'secret'
```

The quotes around each value are added by the application. They tell MySQL that
the username and password are string literals.

The vulnerability exists because the application inserts untrusted input into
the SQL source before sending it to MySQL. A quote inside the input is therefore
interpreted by MySQL as SQL syntax, rather than always remaining part of the
username or password.

## OR injection in the password field

Suppose the username is `alice` and the password input is:

```text
a' OR '1'='1' --
```

The application still adds its own surrounding quotes. The resulting query is:

```sql
SELECT * FROM users
WHERE username = 'alice' AND password = 'a' OR '1'='1' -- '
```

Read the password portion from left to right:

```sql
password = 'a' OR '1'='1'
```

The first quote in the input closes the string literal that began before the
input:

```sql
password = 'a'
```

After that quote, `OR '1'='1'` is no longer password text. It is a new SQL
condition. The condition `'1'='1'` is always true.

The `--` starts a SQL comment in MySQL when followed by whitespace. Therefore,
the application's final quote and the rest of the password expression are
ignored:

```sql
-- '
```

The effective condition is therefore:

```sql
username = 'alice' AND password = 'a' OR '1'='1'
```

SQL evaluates `AND` before `OR`, so the condition is effectively:

```sql
(username = 'alice' AND password = 'a') OR TRUE
```

That condition is true for every row. The query returns the first matching row
because the application calls `fetchone()`.

### Why a single quote alone fails

If the password is only:

```text
'
```

the application creates:

```sql
password = 'a'''
```

The input quote closes the original string, but nothing follows it to create a
valid condition or comment. The quote added by the application leaves the SQL
with an invalid or unintended structure, so MySQL reports a syntax error or
returns no useful result.

The quote is useful only because it changes where the SQL string ends. The rest
of the payload must then form valid SQL and usually comments out the remaining
application generated text.

## Comment injection in the username field

The username can also be used to remove the password check. Suppose the input
is:

```text
john' -- 
```

and the password is anything. The resulting query is:

```sql
SELECT * FROM users
WHERE username = 'john' -- ' AND password = 'anything'
```

The quote after `john` closes the username string:

```sql
username = 'john'
```

The `-- ` then begins a comment. MySQL ignores the application's remaining
quote and the entire password condition:

```sql
-- ' AND password = 'anything'
```

The effective query is:

```sql
SELECT * FROM users
WHERE username = 'john'
```

This does not make the condition true for every user. It simply makes the
database check the username and ignore the password.

## The core idea

The attacker is not asking the application to use a strange username or
password. The attacker is supplying characters that alter the SQL source the
application constructs.

The general sequence is:

1. Close the string literal created by the application.
2. Add a SQL condition or operator.
3. Use a comment when necessary to ignore the remaining application generated
   SQL.

This works because the application concatenates input into SQL instead of using
parameterized queries. In a secure implementation, the database driver would
receive the SQL structure and the input values separately, so a quote in the
input would remain data rather than becoming SQL syntax.