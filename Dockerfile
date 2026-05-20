FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY .env.example ./

ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=backend.app.py
ENV FLASK_RUN_HOST=0.0.0.0

EXPOSE 5000
CMD ["python", "backend/app.py"]
