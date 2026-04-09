FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/FasterApiWeb/FasterAPI"
LABEL org.opencontainers.image.description="FasterAPI — High-performance ASGI web framework"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY pyproject.toml README.md ./
COPY FasterAPI/ FasterAPI/

RUN pip install --no-cache-dir .[all]

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
