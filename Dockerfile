FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY . .
RUN useradd -m travis && mkdir -p /data && chown travis /data
USER travis
ENV TRAVIS_DB=/data/travis.db
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "travis.main:app", "--app-dir", "server", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
