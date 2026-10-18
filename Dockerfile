FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend /app/backend
COPY frontend /app/frontend
EXPOSE 8000
# POS_API_KEY must be supplied at runtime; use a secrets manager.
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
