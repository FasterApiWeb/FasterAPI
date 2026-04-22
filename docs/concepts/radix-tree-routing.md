# Radix Tree Routing

FasterAPI's router is built on a **radix tree** (also called a Patricia trie or
compressed prefix tree).  This data structure enables **O(k)** route resolution —
where *k* is the number of path segments — regardless of how many routes are
registered.

## The problem with alternative approaches

### Linear scan (O(n))

The simplest router iterates through a list of route patterns and returns the first
match:

```python
for pattern, handler in routes:
    match = pattern.match(path)
    if match:
        return handler, match.groupdict()
```

This is O(n) in the number of registered routes.  With 200 routes the 200th route
is 200× slower to resolve than the first.

### Compiled regex (O(n) with lower constant)

Frameworks like older versions of Flask/Werkzeug compile routes into a single
large regex with named groups.  Still O(n) — a big regex must be re-evaluated
against every alternative until one matches.

### Radix tree (O(k))

Resolution time depends only on the **length of the URL path**, not on the number
of registered routes.  1 route or 10,000 routes — same speed.

## How a radix tree works

A radix tree stores strings in a **trie** (character-by-character tree), but
**compresses** paths that have only one child into a single node.

### Building the tree

Given these routes:

```
GET /users
GET /users/{id}
GET /users/{id}/posts
POST /users
GET /items
GET /items/{id}
```

The tree looks like:

```
root
├── "users"          [GET, POST]
│   └── "*" (param: id)   [GET]
│       └── "posts"  [GET]
└── "items"          [GET]
    └── "*" (param: id)   [GET]
```

Each node stores:
- `children`: a `dict[str, RadixNode]` — fast O(1) lookup per segment
- `handlers`: a `dict[str, (handler, metadata)]` — keyed by HTTP method
- `param_name`: name of the path parameter if this node is a wildcard (`*`)

### Resolving a path

To resolve `GET /users/42/posts`:

1. Split into segments: `["users", "42", "posts"]`
2. Start at root, index = 0
3. Look up `"users"` in root's children → found, move to `users` node, index = 1
4. Look up `"42"` in `users.children` → not found; try `"*"` → found (param node), capture `id = "42"`, index = 2
5. Look up `"posts"` in `param.children` → found, move to `posts` node, index = 3
6. Index == len(segments), check `posts.handlers["GET"]` → return handler + `{"id": "42"}`

**Total operations**: 3 dict lookups — one per path segment.  For a path with k
segments, always k lookups regardless of the route count.

## FasterAPI's implementation

The source is in `FasterAPI/router.py`.  Key design choices:

### Iterative traversal

```python
def _walk(self, node, segments, idx, params):
    n = len(segments)
    while idx < n:
        seg = segments[idx]
        child = node.children.get(seg)    # O(1) dict lookup
        if child is not None:
            node = child
            idx += 1
            continue
        param_child = node.children.get("*")   # O(1)
        if param_child is not None:
            params[param_child.param_name] = seg
            node = param_child
            idx += 1
            continue
        return None  # no match
    return node if node.handlers else None
```

**Why iterative?** Recursive calls add stack frames.  At O(k) depth, a route
with 10 segments would create 10 stack frames per request.  The iterative `while`
loop avoids this overhead entirely.

### `__slots__` on every node

```python
class RadixNode:
    __slots__ = ("children", "handlers", "param_name", "is_param")
```

`__slots__` eliminates the per-instance `__dict__`, reducing memory per node by
~50 bytes and speeding up attribute access (no hash lookup through `__dict__`).
With thousands of nodes in a large application, this is significant.

### Static routes checked before parameters

```python
child = node.children.get(seg)   # try exact match first
if child is not None:
    ...
param_child = node.children.get("*")   # fall back to param wildcard
```

The priority order — static segments before wildcard parameters — ensures that
`/users/me` resolves to its dedicated handler rather than the `{id}` wildcard
when both are registered:

```python
@app.get("/users/me")         # resolves first for /users/me
async def get_current_user(): ...

@app.get("/users/{id}")       # resolves for /users/42, /users/123, etc.
async def get_user(id: int): ...
```

### Path splitting

```python
def _split(path: str) -> list[str]:
    return [s for s in path.split("/") if s]
```

`str.split("/")` runs in C and returns a list in a single pass.  The list
comprehension filters empty strings (from leading/trailing slashes).  This is
meaningfully faster than repeated `str.partition("/")` or regex splitting.

## Complexity summary

| Operation | Complexity | Notes |
|---|---|---|
| Route registration | O(k) | k = path segments; done once at startup |
| Route resolution | O(k) | k = segments in the incoming path |
| Memory per route | O(k) | Shared prefix nodes reduce total memory |
| Static route lookup | O(k) dictionary lookups | Python `dict.get` is O(1) average |
| Parametric route lookup | O(k) | Same; falls back to `"*"` key |

Contrast with regex-based routers where both registration and resolution are O(n)
in the number of routes.

## Benchmark results

Routing benchmark from `benchmarks/compare.py` with 100 routes registered
(50 static, 30 single-param, 20 multi-param):

| Path | FasterAPI RadixRouter | Regex router | Speedup |
|---|---|---|---|
| `/health` (static) | ~4,200,000 lookups/s | ~850,000 lookups/s | ~5× |
| `/users/{id}` (1 param) | ~3,800,000 lookups/s | ~620,000 lookups/s | ~6× |
| `/users/{id}/posts/{pid}` (2 params) | ~3,100,000 lookups/s | ~490,000 lookups/s | ~6× |

## Limitations

### No regex constraints in path parameters

FasterAPI parameters use `{name}` syntax only.  There is no built-in constraint
like `{id:\d+}`.  Validate the value inside the handler or using the type
annotation:

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):  # msgspec validates it is an integer
    ...
```

### No optional path segments

Path segments cannot be optional in the URL pattern.  Use query parameters for
optional values:

```python
# Instead of /items/{id?} (not supported), use:
@app.get("/items/{item_id}")
async def get_item(item_id: int, version: int = 1):   # version is a query param
    ...
```

### No catch-all wildcards

There is no `{path:path}` glob matching for arbitrary sub-paths.  Mount a
sub-application for dynamic path prefixes (see [Sub-applications](../advanced/sub-applications.md)).

## Extending the router

`RadixRouter` is exposed as a public class.  You can inspect it:

```python
from FasterAPI.router import RadixRouter

router = RadixRouter()
router.add_route("GET", "/users/{id}", handler, metadata={})

result = router.resolve("GET", "/users/42")
# (handler, {"id": "42"}, {})
```

## Next steps

- [Architecture](../architecture.md) — how the router fits into the full request lifecycle.
- [Benchmarks Deep Dive](../benchmark-methodology.md) — how routing benchmarks are run.
- [Bigger Applications](../advanced/bigger-apps.md) — organising routes with `FasterRouter`.
