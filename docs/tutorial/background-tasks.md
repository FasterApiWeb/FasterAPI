# Background Tasks

Background tasks run **after the response is sent** to the client — useful for
sending emails, writing audit logs, or triggering slow processes without blocking
the HTTP response.

## Injecting `BackgroundTasks`

Declare a `BackgroundTasks` parameter (the type annotation is the trigger):

```python
from FasterAPI import Faster, BackgroundTasks

app = Faster()


def write_log(message: str) -> None:
    with open("log.txt", "a") as f:
        f.write(message + "\n")


@app.post("/send-notification")
async def send_notification(email: str, tasks: BackgroundTasks):
    tasks.add_task(write_log, f"notification sent to {email}")
    return {"message": "Notification queued"}
```

The response is returned immediately; `write_log` runs afterwards.

## Async background tasks

```python
import asyncio


async def send_email(to: str, subject: str) -> None:
    await asyncio.sleep(0.5)  # simulate async I/O
    print(f"Email sent to {to}: {subject}")


@app.post("/register")
async def register(email: str, tasks: BackgroundTasks):
    tasks.add_task(send_email, email, "Welcome to FasterAPI!")
    return {"registered": email}
```

## Multiple tasks

```python
@app.post("/order")
async def place_order(order_id: int, tasks: BackgroundTasks):
    tasks.add_task(write_log, f"order {order_id} placed")
    tasks.add_task(send_email, "warehouse@example.com", f"New order {order_id}")
    return {"order_id": order_id, "status": "placed"}
```

Tasks execute in the order they were added.

## Background tasks in dependencies

```python
from FasterAPI import Depends


async def audit_log(tasks: BackgroundTasks, action: str):
    tasks.add_task(write_log, action)


@app.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    tasks: BackgroundTasks,
):
    await audit_log(tasks, f"deleted item {item_id}")
    return {"deleted": item_id}
```

## Error handling

If a background task raises an exception, it is **not** propagated to the client
(the response has already been sent). Log exceptions inside the task:

```python
async def safe_task():
    try:
        await do_risky_work()
    except Exception as exc:
        print(f"Background task failed: {exc}")
```

## When to use background tasks vs sub-interpreters

| Scenario | Recommended approach |
|---|---|
| I/O-bound work (email, DB write) | `BackgroundTasks` |
| CPU-bound work (image processing) | `SubInterpreterPool` / `run_in_subinterpreter` |

See [Concurrency & Parallelism](../concepts/concurrency.md) for details.

## Next steps

- [Middleware](middleware.md) — apply logic to every request.
- [Dependencies](dependencies.md) — inject `BackgroundTasks` via `Depends()`.
