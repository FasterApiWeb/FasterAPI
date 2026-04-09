# Getting started

Use **Python 3.13** if you can (see [Python 3.13 & compatibility](python-313.md)); the minimum
supported release is **3.10**. Create a **virtual environment** before installing dependencies.

## Install

```bash
pip install faster-api-web
```

Optional **uvloop** (recommended on Linux for lower event-loop overhead):

```bash
pip install faster-api-web[all]
```

For **`TestClient`** (integration tests), add **httpx**:

```bash
pip install faster-api-web[test]
```

## Minimal application

Create `main.py`:

```python
import msgspec
from FasterAPI import Faster

app = Faster()


class Item(msgspec.Struct):
    name: str
    price: float


@app.get("/items/{item_id}")
async def read_item(item_id: str):
    return {"item_id": item_id}


@app.post("/items")
async def create_item(item: Item):
    return {"received": item}
```

## Run with Uvicorn

```bash
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive OpenAPI UI (if enabled).

## Imports at a glance

- **Application class:** `from FasterAPI import Faster` (or `from FasterAPI.app import Faster`).
- **Path/query/body helpers:** `Path`, `Query`, `Body`, … from `FasterAPI`.
- **Models:** use **`msgspec.Struct`**, not Pydantic, for validated JSON bodies by default.

## Next steps

- Follow the [CRUD tutorial](tutorial-crud.md).
- If you already use FastAPI, read [Migrating from FastAPI](migration-from-fastapi.md).
