"""Basic FasterAPI application example."""

from FasterAPI.app import Faster
from FasterAPI.params import Query

app = Faster(title="Basic App", version="1.0.0")


@app.get("/", summary="Root endpoint")
async def root():
    return {"message": "Hello, FasterAPI!"}


@app.get("/items", tags=["items"], summary="List items")
async def list_items(skip: int = Query(0), limit: int = Query(10)):
    return {"skip": skip, "limit": limit, "items": []}


@app.get("/items/{item_id}", tags=["items"], summary="Get item by ID")
async def get_item(item_id: str):
    return {"item_id": item_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
