# OAuth2 with Password Flow & JWT Tokens

This guide implements a complete login-and-token authentication system using the
**OAuth2 Password flow** and **JSON Web Tokens (JWT)**.

## Install dependencies

```bash
pip install python-jose[cryptography] passlib[bcrypt]
```

- `python-jose` — JWT encode/decode
- `passlib` — password hashing (bcrypt)

## Configuration

```python
# auth.py
import os
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
```

## User models

```python
import msgspec


class UserInDB(msgspec.Struct):
    username: str
    email: str
    hashed_password: str
    disabled: bool = False


class User(msgspec.Struct):
    username: str
    email: str
    disabled: bool = False


class TokenResponse(msgspec.Struct):
    access_token: str
    token_type: str = "bearer"
```

## Fake user database (replace with real DB)

```python
from auth import hash_password

_fake_users_db: dict[str, UserInDB] = {
    "alice": UserInDB(
        username="alice",
        email="alice@example.com",
        hashed_password=hash_password("secret"),
    )
}
```

## Auth dependency

```python
from FasterAPI import Header, HTTPException, Depends
from auth import decode_access_token


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> User:
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not authorization or not authorization.startswith("Bearer "):
        raise credentials_exception

    token = authorization.removeprefix("Bearer ")
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    username: str | None = payload.get("sub")
    if username is None:
        raise credentials_exception

    user_data = _fake_users_db.get(username)
    if user_data is None or user_data.disabled:
        raise credentials_exception

    return User(username=user_data.username, email=user_data.email)
```

## Login endpoint

```python
from FasterAPI import Faster, Form
from datetime import timedelta
from auth import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

app = Faster()


@app.post("/auth/token", tags=["auth"])
async def login(username: str = Form(), password: str = Form()) -> TokenResponse:
    user = _fake_users_db.get(username)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        {"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=token)
```

## Protected routes

```python
@app.get("/users/me", tags=["users"])
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@app.get("/items", tags=["items"])
async def list_items(current_user: User = Depends(get_current_user)):
    return [{"name": "Widget", "owner": current_user.username}]
```

## Try it out

```bash
# Get a token
curl -X POST http://localhost:8000/auth/token \
  -d "username=alice&password=secret"
# {"access_token":"eyJ...","token_type":"bearer"}

# Use the token
curl http://localhost:8000/users/me \
  -H "Authorization: Bearer eyJ..."
```

## Token refresh

For long-lived sessions, issue a **refresh token** alongside the access token and
provide a `/auth/refresh` endpoint.  Store refresh tokens in an httpOnly cookie and
short-lived access tokens in memory.

## Next steps

- [OAuth2 Scopes](oauth2-scopes.md) — role-based / permission-based access.
- [HTTP Basic Auth](http-basic-auth.md) — simpler alternative for internal tools.
