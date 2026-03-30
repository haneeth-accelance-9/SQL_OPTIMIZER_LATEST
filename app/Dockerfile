  FROM python:3.11-slim as builder

  WORKDIR /app
  ENV PYTHONDONTWRITEBYTECODE=1
  ENV PIP_NO_CACHE_DIR=1

  RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc \
      libcairo2-dev \
      pkg-config \
      && rm -rf /var/lib/apt/lists/*

  RUN pip install --upgrade pip
  COPY requirements.txt .
  RUN pip install --prefix=/install -r requirements.txt

  FROM python:3.11-slim as runtime

  WORKDIR /app
  ENV PYTHONDONTWRITEBYTECODE=1
  ENV PYTHONUNBUFFERED=1
  ENV DJANGO_SETTINGS_MODULE=sql_license_optimizer.settings

  # Non-root user
  RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --shell /bin/bash --create-home app

  COPY --from=builder /install /usr/local
  COPY . .
  RUN python -c "import django; print(django.__file__)"  # ensure deps are importable

  # Static and media dirs writable by app
  RUN mkdir -p staticfiles uploads logs && chown -R app:app /app

  USER app

  EXPOSE 8000
  # CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "sql_license_optimizer.wsgi:application"]
  # CMD ["sh", "-c", "python manage.py migrate --no-input && gunicorn --bind 0.0.0.0:8000 --workers 2 sql_license_optimizer.wsgi:application"]
  CMD ["sh", "-c", "python manage.py migrate --no-input && python manage.py createsuperuser --no-input || true && gunicorn --bind 0.0.0.0:8000 --workers 2 sql_license_optimizer.wsgi:application"]
