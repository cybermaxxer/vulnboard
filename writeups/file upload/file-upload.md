# malicious file upload: no file type validation

## what the bug is

`/upload` accepts a file from the request and saves it when the filename is not empty. the route does not check the extension, the MIME type, or the file contents:

```python
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        content = request.form.get("content")
        title = request.form.get("title")
        user_id = session.get("user_id")
        if not content or not title:
            return "Content and title are required.", 400
        if not user_id:
            return "You must be logged in to upload.", 401
        db = get_db()
        cursor = db.cursor()
        if file and file.filename:
            filename = file.filename
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            image_path = f"/uploads/{filename}"
            sql_query = f"INSERT INTO posts (title, content, image_path, user_id) VALUES ('{title}', '{content}', '{image_path}', {user_id})"
            cursor.execute(sql_query)
            db.commit()
            cursor.close()
            return f"File '{filename}' uploaded successfully!"
```

once `file.filename` has a value, the route immediately saves the file. there is no allowlist such as `.jpg` or `.png`, no comparison with `file.content_type`, and no inspection of the file's magic bytes. the route trusts the filename supplied by the client.

## real jpg test

1. log in to the local app.
2. open `/upload`.
3. submit a real jpg with a title and content.
4. confirm that the response says:

```text
File 'photo.jpg' uploaded successfully!
```

5. confirm that the file exists in the container at:

```text
/app/uploads/photo.jpg
```

6. open `/see` and confirm that the post stores the image path:

```text
/uploads/photo.jpg
```

one reproducible command after creating a real local image is:

```bash
curl -i -b john.cookies -c john.cookies \
  -F "title=real image" \
  -F "content=jpg upload test" \
  -F "file=@photo.jpg;type=image/jpeg" \
  http://127.0.0.1:5000/upload
```

## renamed binary test

create a file containing arbitrary bytes and give it a jpg filename:

```bash
printf 'this is not a jpeg file' > evil.jpg
```

upload it with the same form:

```bash
curl -i -b john.cookies -c john.cookies \
  -F "title=renamed binary" \
  -F "content=arbitrary binary upload test" \
  -F "file=@evil.jpg;type=image/jpeg" \
  http://127.0.0.1:5000/upload
```

expected result:

```text
File 'evil.jpg' uploaded successfully!
```

this file is not a real JPEG, but the route still accepts and saves it because the filename and the client supplied MIME type are enough to pass the only condition in the route:

```python
if file and file.filename:
```

confirm the saved bytes from inside the web container:

```bash
docker compose exec web sh -c 'ls -l /app/uploads/evil.jpg && wc -c /app/uploads/evil.jpg'
```

## code review confirmation

reading the route confirms that the upload has zero file type validation:

| check | present |
|---|---|
| extension allowlist | no |
| MIME type validation | no |
| magic byte validation | no |
| image parser validation | no |
| filename presence check | yes |
| file save | yes |

`file.filename` is used as the saved filename, and `file.save(...)` runs without checking whether the bytes represent the claimed file type. the database stores the resulting path as an image path even when the uploaded content is not an image.

## why this matters

an extension is only a label supplied by the client. a MIME type in a multipart request is also supplied by the client. neither proves what the file contains. checking magic bytes or parsing the file would provide stronger evidence of its type.

in this phase, the vulnerability is that the application accepts arbitrary content while presenting it as an uploaded image. later behavior depends on how the stored file is served or processed, but this route itself performs no validation.

## verification status

| check | result |
|---|---|
| route has no extension allowlist | confirmed by reading `logic/__init__.py` |
| route has no MIME check | confirmed by reading `logic/__init__.py` |
| route has no magic byte check | confirmed by reading `logic/__init__.py` |
| real jpg is accepted and saved | manual Docker test pending |
| renamed arbitrary binary is accepted and saved | manual Docker test pending |
