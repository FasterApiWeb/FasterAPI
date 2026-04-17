# Python Type Hints Introduction

FasterAPI relies heavily on Python **type hints** to declare parameter types,
validate inputs, and generate OpenAPI documentation automatically.

## What are type hints?

Type hints are annotations that tell Python (and tools like mypy) the *intended* type
of a variable, parameter, or return value.  Python does **not** enforce them at
runtime by default — FasterAPI uses them to do so for HTTP parameters.

```python
def greet(name: str) -> str:
    return f"Hello, {name}"
```

## Basic types

```python
x: int = 42
y: float = 3.14
z: str = "hello"
b: bool = True
raw: bytes = b"\x00"
```

## Collections

```python
from typing import Any

items: list[str] = ["a", "b"]
mapping: dict[str, int] = {"x": 1}
pair: tuple[int, str] = (1, "one")
unique: set[int] = {1, 2, 3}
anything: list[Any] = [1, "two", 3.0]
```

## Optional values

```python
# Python 3.10+
name: str | None = None

# Python 3.9 and earlier
from typing import Optional
name: Optional[str] = None
```

`str | None` means the value is either a `str` or `None`.

## Union types

```python
# Python 3.10+
value: int | str | float

# Earlier versions
from typing import Union
value: Union[int, str, float]
```

## How FasterAPI uses type hints

### Path and query parameters

```python
@app.get("/items/{item_id}")
async def get_item(
    item_id: int,          # coerced from URL string to int
    active: bool = True,   # query param, default True
    limit: int = 10,       # query param, default 10
):
    ...
```

FasterAPI reads the annotations and automatically:
- Extracts `item_id` from the URL and converts it to `int`.
- Extracts `active` and `limit` from the query string.
- Returns a **422** error with a clear message if coercion fails.

### Request bodies with msgspec

```python
import msgspec

class Item(msgspec.Struct):
    name: str                    # required string
    price: float                 # required float
    tags: list[str] = []         # optional, defaults to empty list
    description: str | None = None  # optional, nullable
```

FasterAPI uses `msgspec`'s type information to validate and decode the JSON body.

### Return types

```python
@app.get("/items/{item_id}")
async def get_item(item_id: int) -> Item:
    return Item(name="Widget", price=9.99)
```

The return type annotation drives OpenAPI schema generation for the response.

## msgspec type support

`msgspec` supports a rich set of types for struct fields:

| Python type | JSON representation |
|---|---|
| `int`, `float` | number |
| `str` | string |
| `bool` | true / false |
| `bytes` | base64-encoded string |
| `list[T]`, `tuple[T, ...]` | array |
| `dict[str, V]` | object |
| `T \| None` | value or null |
| Nested `Struct` | nested object |
| `Literal["a", "b"]` | enum-like string |
| `datetime` | ISO 8601 string |
| `UUID` | UUID string |

## Type checking with mypy

Add mypy to your development workflow:

```bash
pip install mypy
mypy main.py --strict
```

Or add to `pyproject.toml`:

```toml
[tool.mypy]
strict = true
```

FasterAPI and msgspec both ship type stubs.

## Type checking with ruff

```bash
pip install ruff
ruff check .
```

## Next steps

- [Request Body](../tutorial/request-body.md) — using msgspec structs in routes.
- [Dependencies](../tutorial/dependencies.md) — type-annotated dependency injection.
