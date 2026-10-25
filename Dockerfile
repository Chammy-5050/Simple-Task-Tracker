FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home appuser

COPY --chown=appuser:appuser . .
RUN mkdir -p /app/media /app/staticfiles \
    && chown appuser:appuser /app/media /app/staticfiles
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py createcachetable && python manage.py collectstatic --noinput && gunicorn taskTracker.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60"]