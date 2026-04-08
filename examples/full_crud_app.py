"""Complete in-memory CRUD API with all FasterAPI features.

Run:
    python examples/full_crud_app.py

Then visit:
    http://localhost:8000/docs   — Full Swagger documentation
    http://localhost:8000/redoc  — ReDoc documentation

Features demonstrated:
    - FasterRouter with /users prefix
    - User model with msgspec Struct validation
    - Full CRUD: list, get, create, update, delete
    - Background task logging on creation
    - CORS middleware
    - Dependency injection
    - Tags and descriptions for all routes
    - Custom exception handling
    - 404/422 error responses
"""

import logging
import time

import msgspec

from FasterAPI import (
    BackgroundTasks,
    CORSMiddleware,
    Depends,
    Faster,
    FasterRouter,
    HTTPException,
    Path,
    Query,
    Request,
)

# ── Logging setup ──

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger("crud_app")


# ── Models ──

class UserCreate(msgspec.Struct):
    """Payload for creating a new user."""
    name: str
    email: str


class UserUpdate(msgspec.Struct):
    """Payload for updating an existing user. All fields optional."""
    name: str | None = None
    email: str | None = None


# ── In-memory store ──

_db: dict[str, dict] = {}
_counter: int = 0


def _next_id() -> str:
    global _counter
    _counter += 1
    return str(_counter)


# ── Dependencies ──

async def get_db() -> dict:
    """Provide the in-memory database."""
    return _db


async def get_user_or_404(
    user_id: str = Path(description="The user's unique ID"),
    db: dict = Depends(get_db),
) -> dict:
    """Look up a user by ID, raising 404 if not found."""
    if user_id not in db:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return db[user_id]


# ── Background tasks ──

def log_user_created(user_id: str, name: str) -> None:
    """Log that a new user was created (runs after response is sent)."""
    logger.info("User created: id=%s name=%s", user_id, name)


# ── Router ──

router = FasterRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    summary="List all users",
    response_model=UserCreate,
)
async def list_users(
    skip: str = Query("0"),
    limit: str = Query("20"),
    db: dict = Depends(get_db),
):
    """Return a paginated list of all users."""
    users = list(db.values())
    return users[int(skip) : int(skip) + int(limit)]


@router.get(
    "/{user_id}",
    summary="Get a user by ID",
    response_model=UserCreate,
)
async def get_user(user: dict = Depends(get_user_or_404)):
    """Fetch a single user. Returns 404 if the ID doesn't exist."""
    return user


@router.post(
    "",
    summary="Create a new user",
    status_code=201,
    response_model=UserCreate,
)
async def create_user(
    body: UserCreate,
    bg: BackgroundTasks,
    db: dict = Depends(get_db),
):
    """Create a user from the JSON body. Logs the creation in the background."""
    user_id = _next_id()
    user = {
        "id": user_id,
        "name": body.name,
        "email": body.email,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    db[user_id] = user
    bg.add_task(log_user_created, user_id, body.name)
    return user


@router.put(
    "/{user_id}",
    summary="Update a user",
    response_model=UserCreate,
)
async def update_user(
    body: UserUpdate,
    user: dict = Depends(get_user_or_404),
):
    """Update a user's fields. Only provided fields are changed."""
    if body.name is not None:
        user["name"] = body.name
    if body.email is not None:
        user["email"] = body.email
    return user


@router.delete(
    "/{user_id}",
    summary="Delete a user",
)
async def delete_user(
    user_id: str = Path(),
    db: dict = Depends(get_db),
):
    """Remove a user by ID. Returns 404 if not found."""
    if user_id not in db:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    del db[user_id]
    return {"deleted": user_id}


# ── App assembly ──

app = Faster(
    title="User Management API",
    version="1.0.0",
    description="A complete CRUD API built with FasterAPI — demonstrating "
                "routing, validation, dependency injection, background tasks, "
                "and middleware.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(router)


@app.get("/", tags=["root"], summary="Health check")
async def health():
    """Simple health check endpoint."""
    return {"status": "ok", "users": len(_db)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
