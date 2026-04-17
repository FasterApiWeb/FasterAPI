# Request Body

A **request body** is data sent by the client in the HTTP request, typically as JSON.
FasterAPI uses **[msgspec](https://jcristharif.com/msgspec/)** structs for fast,
type-safe validation and serialisation — no Pydantic required.

## Defining a model

Subclass `msgspec.Struct` to describe the expected fields:

```python
import msgspec


class Item(msgspec.Struct):
    name: str
    price: float
    in_stock: bool = True
```

- Required fields have no default (`name`, `price`).
- Optional fields have a default (`in_stock`).

## Using the model in a route

Declare the struct as a parameter. FasterAPI reads the JSON body, validates it, and
passes an `Item` instance to your handler:

```python
from FasterAPI import Faster
import msgspec

app = Faster()


class Item(msgspec.Struct):
    name: str
    price: float
    in_stock: bool = True


@app.post("/items")
async def create_item(item: Item):
    return {"name": item.name, "price": item.price}
```

```bash
curl -X POST http://localhost:8000/items \
  -H "Content-Type: application/json" \
  -d '{"name": "Widget", "price": 9.99}'
# {"name":"Widget","price":9.99}
```

## Path + query + body together

```python
@app.put("/items/{item_id}")
async def update_item(item_id: int, item: Item, notify: bool = False):
    result = {"item_id": item_id, **msgspec.structs.asdict(item)}
    if notify:
        result["message"] = "notified"
    return result
```

- `item_id` comes from the path.
- `notify` comes from the query string.
- `item` comes from the JSON body.

## Nested models

```python
class Image(msgspec.Struct):
    url: str
    width: int
    height: int


class Product(msgspec.Struct):
    name: str
    image: Image | None = None
```

## Optional body

Use `| None` with a default to make the body optional:

```python
@app.patch("/items/{item_id}")
async def partial_update(item_id: int, item: Item | None = None):
    if item is None:
        return {"item_id": item_id, "updated": False}
    return {"item_id": item_id, "name": item.name}
```

## Validation errors

If the client sends invalid JSON or a field fails type coercion, FasterAPI returns:

```json
{
  "detail": [
    {
      "loc": ["body"],
      "msg": "Expected `float`, got `str` - at `$.price`",
      "type": "value_error.msgspec"
    }
  ]
}
```

## Using `Body()` for raw JSON

For cases where you want an arbitrary JSON value rather than a struct:

```python
from FasterAPI import Body


@app.post("/raw")
async def echo(data: dict = Body()):
    return data
```

## Next steps

- [Response Model](response-model.md) — control what data is returned to the client.
- [Form Data & File Uploads](form-and-files.md) — non-JSON request bodies.
- [Dependencies](dependencies.md) — share validation logic across routes.
