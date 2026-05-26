FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME ["/data"]

ENV DB_PATH=/data/screentime.db \
    PORT=5000

EXPOSE 5000

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60 --access-logfile - --error-logfile -"]
