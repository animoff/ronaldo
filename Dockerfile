# Docker — дополнительный путь. Для первого урока достаточно обычного Python.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --requirement requirements.txt
RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
RUN mkdir -p /app/staticfiles /app/media && chown -R appuser:appuser /app
USER appuser
# Сборке не нужны production-секреты: эта команда только собирает CSS/admin static.
RUN DEBUG=0 SECRET_KEY=build-only-public-key-not-used-by-the-running-application python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "ronaldu.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-"]
