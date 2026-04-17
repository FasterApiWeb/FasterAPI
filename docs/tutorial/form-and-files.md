# Form Data & File Uploads

HTML forms and file uploads use `multipart/form-data` or
`application/x-www-form-urlencoded` — not JSON.  FasterAPI handles both with the
`Form()`, `File()`, and `UploadFile` helpers.

## Form fields

```python
from FasterAPI import Faster, Form

app = Faster()


@app.post("/login")
async def login(username: str = Form(), password: str = Form()):
    return {"username": username}
```

```bash
curl -X POST http://localhost:8000/login \
  -d "username=alice&password=secret"
```

!!! note
    You cannot mix `Form()` fields and a JSON body (`msgspec.Struct`) in the same
    endpoint — HTTP only allows one body encoding per request.

## Uploading a single file

```python
from FasterAPI import Faster, UploadFile, File

app = Faster()


@app.post("/upload")
async def upload_file(file: UploadFile = File()):
    contents = await file.read()
    return {"filename": file.filename, "size": len(contents)}
```

`UploadFile` exposes:

| Attribute / method | Description |
|--------------------|-------------|
| `filename` | Original filename from the client |
| `content_type` | MIME type (e.g. `image/png`) |
| `await file.read()` | Read all bytes |
| `await file.read(n)` | Read up to *n* bytes |

## Multiple files

```python
@app.post("/multi-upload")
async def multi_upload(files: list[UploadFile] = File()):
    return [{"filename": f.filename} for f in files]
```

## Mixed form and file

Combine `Form()` and `File()` fields freely:

```python
@app.post("/profile")
async def update_profile(
    bio: str = Form(),
    avatar: UploadFile = File(),
):
    data = await avatar.read()
    return {"bio": bio, "avatar_size": len(data)}
```

## Form with optional file

```python
@app.post("/create-post")
async def create_post(
    title: str = Form(),
    image: UploadFile | None = File(default=None),
):
    return {"title": title, "has_image": image is not None}
```

## Accessing raw form data

```python
from FasterAPI import Request


@app.post("/raw-form")
async def raw_form(request: Request):
    form = await request.form()
    return dict(form)
```

## Next steps

- [Error Handling](error-handling.md) — what happens when validation fails.
- [Dependencies](dependencies.md) — reuse form parsing across routes.
