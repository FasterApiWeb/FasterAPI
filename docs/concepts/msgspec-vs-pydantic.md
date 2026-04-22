# msgspec vs Pydantic

FasterAPI uses **msgspec** for validation and serialization instead of Pydantic.
This page explains the design philosophy behind each library, where they differ,
when each one shines, and how to migrate existing Pydantic code.

## Philosophy

| | msgspec | Pydantic v2 |
|---|---|---|
| **Primary goal** | Zero-copy serialization + validation in C | Developer-friendly validation with rich error messages |
| **Schema definition** | `msgspec.Struct` (immutable, `__slots__`-based) | `pydantic.BaseModel` (mutable, supports `__init__` customisation) |
| **Validation timing** | At decode/encode boundary only | On attribute assignment (with `model_validate`) |
| **Type coercion** | Strict by default (no silent coercion) | Lenient by default (`"42"` → `42`) |
| **Error detail** | Compact, path-based | Verbose, human-readable with loc/msg/type |
| **Speed** | ~5–10× faster than Pydantic v2 for encode/decode | Fast (Rust core), slower than msgspec |
| **Memory** | Lower (Structs use `__slots__`, no instance `__dict__`) | Higher (BaseModel has more metadata overhead) |
| **Ecosystem** | Self-contained | Rich ecosystem (validators, serializers, settings) |

## Performance comparison

Benchmark on Apple Silicon (Python 3.13, 1 M iterations):

| Operation | msgspec | Pydantic v2 | Speedup |
|---|---|---|---|
| JSON encode | ~1,400,000 ops/s | ~280,000 ops/s | ~5× |
| JSON decode + validate | ~950,000 ops/s | ~180,000 ops/s | ~5× |
| Object construction | ~8,000,000 ops/s | ~1,500,000 ops/s | ~5× |

These numbers are from `benchmarks/compare.py`.  See the
[Benchmark Methodology](../benchmark-methodology.md) page for reproduction steps.

## API comparison

### Defining schemas

=== "msgspec"

    ```python
    import msgspec

    class Address(msgspec.Struct):
        street: str
        city: str
        zip_code: str

    class User(msgspec.Struct):
        id: int
        name: str
        email: str
        age: int | None = None
        address: Address | None = None
        tags: list[str] = []
    ```

=== "Pydantic"

    ```python
    from pydantic import BaseModel

    class Address(BaseModel):
        street: str
        city: str
        zip_code: str

    class User(BaseModel):
        id: int
        name: str
        email: str
        age: int | None = None
        address: Address | None = None
        tags: list[str] = []
    ```

### Decoding / validating

=== "msgspec"

    ```python
    import msgspec

    json_bytes = b'{"id": 1, "name": "Alice", "email": "alice@example.com"}'

    # Decode JSON bytes directly into a typed Struct
    user = msgspec.json.decode(json_bytes, type=User)
    print(user.name)   # Alice

    # Validate from a dict (Python object)
    user = msgspec.convert({"id": 1, "name": "Alice", "email": "a@e.com"}, User)
    ```

=== "Pydantic"

    ```python
    from pydantic import TypeAdapter

    json_bytes = b'{"id": 1, "name": "Alice", "email": "alice@example.com"}'

    # Validate from JSON bytes
    adapter = TypeAdapter(User)
    user = adapter.validate_json(json_bytes)

    # Validate from dict
    user = User.model_validate({"id": 1, "name": "Alice", "email": "a@e.com"})
    ```

### Encoding / serializing

=== "msgspec"

    ```python
    user = User(id=1, name="Alice", email="alice@example.com")

    # To JSON bytes (fastest path)
    json_bytes = msgspec.json.encode(user)

    # To dict
    data = msgspec.structs.asdict(user)
    ```

=== "Pydantic"

    ```python
    user = User(id=1, name="Alice", email="alice@example.com")

    # To JSON string
    json_str = user.model_dump_json()

    # To dict
    data = user.model_dump()
    ```

### Field customisation

=== "msgspec"

    ```python
    import msgspec

    class Product(msgspec.Struct):
        id: int
        # Rename field in JSON
        internal_name: str = msgspec.field(name="name")
        # Default factory
        tags: list[str] = msgspec.field(default_factory=list)
        # Optional with default
        price: float = 0.0
    ```

=== "Pydantic"

    ```python
    from pydantic import BaseModel, Field

    class Product(BaseModel):
        id: int
        internal_name: str = Field(alias="name")
        tags: list[str] = Field(default_factory=list)
        price: float = 0.0
    ```

### Custom validators

=== "msgspec"

    ```python
    import msgspec

    class Email(str):
        """Custom type that validates email format."""

    # msgspec uses Python's __get_validators__ protocol for custom types
    # For complex validation, use post-decode processing or a custom Encoder/Decoder
    class SignupRequest(msgspec.Struct):
        email: str
        password: str

        def __post_init__(self):
            if "@" not in self.email:
                raise ValueError(f"Invalid email: {self.email}")
            if len(self.password) < 8:
                raise ValueError("Password must be at least 8 characters")
    ```

=== "Pydantic"

    ```python
    from pydantic import BaseModel, field_validator, EmailStr

    class SignupRequest(BaseModel):
        email: EmailStr   # built-in email validator
        password: str

        @field_validator("password")
        @classmethod
        def password_length(cls, v: str) -> str:
            if len(v) < 8:
                raise ValueError("Password must be at least 8 characters")
            return v
    ```

## Key behavioural differences

### Type coercion

msgspec is **strict** — it raises on type mismatches; Pydantic v2 is **lenient**
by default:

```python
import msgspec, json

class Payload(msgspec.Struct):
    count: int

# OK — integer
msgspec.json.decode(b'{"count": 42}', type=Payload)

# Raises msgspec.ValidationError — string not accepted for int
msgspec.json.decode(b'{"count": "42"}', type=Payload)
```

Pydantic would silently coerce `"42"` → `42`.

### Mutability

msgspec Structs are **immutable by default**:

```python
class Point(msgspec.Struct):
    x: float
    y: float

p = Point(1.0, 2.0)
p.x = 3.0   # AttributeError — Struct is frozen

# For a mutable Struct:
class MutablePoint(msgspec.Struct, frozen=False):
    x: float
    y: float
```

Pydantic BaseModel instances are mutable by default.

### Inheritance

```python
# msgspec — single inheritance only, no field override
class Base(msgspec.Struct):
    id: int

class Child(Base):
    name: str   # adds a field

# Pydantic — supports multiple inheritance and field override
class Child(Base):
    name: str
    id: int = 0   # overrides parent field
```

### JSON `null` vs missing field

```python
class Item(msgspec.Struct):
    name: str
    tag: str | None = None

# Both parse correctly in msgspec:
msgspec.json.decode(b'{"name": "x"}', type=Item)           # tag = None
msgspec.json.decode(b'{"name": "x", "tag": null}', type=Item)  # tag = None

# To distinguish missing from null, use msgspec.NODEFAULT sentinel:
import msgspec
MISSING = msgspec.NODEFAULT

class Item(msgspec.Struct):
    name: str
    tag: str | msgspec.UnsetType = msgspec.NODEFAULT
```

## When to choose each

### Choose msgspec when:

- **Maximum throughput** is a priority (high-req/s APIs, real-time systems)
- Schemas are relatively simple (CRUD entities, event payloads)
- You want zero external dependencies beyond msgspec itself
- You're already using FasterAPI (it's the native validation layer)

### Choose Pydantic when:

- You need **complex validators** (`@field_validator`, `@model_validator`)
- You rely on **Pydantic-ecosystem libraries** (pydantic-settings, SQLModel, FastAPI)
- Your team is already experienced with Pydantic
- You need **strict/lenient mode control** per-field
- You need `model_dump(exclude_unset=True)` semantics

### Using both in the same project

FasterAPI uses msgspec for route handler validation.  You can still use Pydantic
for settings or internal domain models:

```python
# settings.py — Pydantic-settings for type-safe env vars
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    debug: bool = False

    class Config:
        env_file = ".env"

settings = Settings()

# routes.py — msgspec for request/response schemas
import msgspec
from FasterAPI import Faster

app = Faster()

class CreateUser(msgspec.Struct):
    username: str
    password: str

@app.post("/users")
async def create_user(body: CreateUser):
    ...
```

## Migration patterns

### From Pydantic BaseModel to msgspec Struct

| Pydantic | msgspec |
|---|---|
| `class M(BaseModel)` | `class M(msgspec.Struct)` |
| `Field(alias="x")` | `msgspec.field(name="x")` |
| `Field(default_factory=list)` | `msgspec.field(default_factory=list)` |
| `model_validate(data)` | `msgspec.convert(data, M)` |
| `model_dump()` | `msgspec.structs.asdict(obj)` |
| `model_dump_json()` | `msgspec.json.encode(obj)` |
| `@field_validator` | `__post_init__` method |
| `Optional[X]` / `X \| None` | `X \| None` (same) |
| `list[X]` | `list[X]` (same) |

### Step-by-step migration

1. Replace `BaseModel` with `msgspec.Struct` in schema files.
2. Replace `Field(...)` with `msgspec.field(...)` where needed.
3. Replace `model_validate` calls with `msgspec.convert`.
4. Replace `model_dump` / `model_dump_json` with `msgspec.structs.asdict` / `msgspec.json.encode`.
5. Move complex validators into `__post_init__` or a separate validation function.
6. Run your tests — msgspec is stricter, so some test inputs may need adjustment.

## Next steps

- [Python Type Hints](types-intro.md) — the type annotation foundations msgspec builds on.
- [Benchmarks Deep Dive](../benchmark-methodology.md) — how the performance numbers are measured.
- [Request Body](../tutorial/request-body.md) — using msgspec Structs in route handlers.
