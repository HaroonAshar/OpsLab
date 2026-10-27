FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "psycopg[binary]"

COPY backend/app.py /app/app.py

ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["python", "app.py"]
