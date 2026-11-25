FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install -e .

RUN useradd --create-home appuser
USER appuser

# Default: API. docker-compose overrides the command for the worker and dashboard.
EXPOSE 8000
CMD ["uvicorn", "trendintel.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
