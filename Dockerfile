FROM python:3.7-alpine
RUN mkdir /app
WORKDIR /app
COPY . /app
RUN apk update && apk add postgresql-dev gcc python3-dev musl-dev linux-headers
RUN  python setup.py install