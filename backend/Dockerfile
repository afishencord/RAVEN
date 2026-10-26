FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping curl openssh-client sshpass \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.in requirements.txt ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
