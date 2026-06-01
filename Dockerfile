FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV MEMORY_MAP_DATA_DIR=/app/data

WORKDIR /app
COPY . /app

RUN mkdir -p /app/data

EXPOSE 8765

CMD ["python", "server.py", "--host", "0.0.0.0"]
