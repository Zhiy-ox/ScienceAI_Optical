# Backend API image for the ScienceAI FastAPI service.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package (and its runtime deps) from the project metadata first,
# so the dependency layer is cached independently of source changes.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

EXPOSE 8000

# Run the ASGI app. Override the worker count via the command in compose.
CMD ["uvicorn", "science_ai.main:app", "--host", "0.0.0.0", "--port", "8000"]
