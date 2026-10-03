FROM python:3.12-slim AS platform
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY requirements-platform.lock ./
RUN pip install --no-cache-dir -r requirements-platform.lock
COPY app ./app
COPY alembic-v2.ini ./
RUN useradd --uid 10001 --create-home platform && mkdir -p /workspace/var/platform && chown -R platform:platform /workspace/var
USER platform
CMD ["uvicorn", "app.v2.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
