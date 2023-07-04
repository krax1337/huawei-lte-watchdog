FROM docker.io/library/python:3.11-slim

ENV PYTHONUNBUFFERED=1

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY ./requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY ./main.py ./

CMD [ "python", "main.py" ]
