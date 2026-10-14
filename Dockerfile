FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

RUN useradd -m appuser
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://localhost:%s/api/health' % os.environ.get('PORT','5000'))"

CMD gunicorn -w 1 --threads 8 --timeout 120 -b 0.0.0.0:${PORT:-5000} app:app