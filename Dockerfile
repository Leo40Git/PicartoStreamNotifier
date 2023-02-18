# syntax=docker/dockerfile:1

FROM python:3.10-slim-buster

ADD picartonotif.py /

RUN pip3 install requests 2.28.1

CMD [ "python3", "picartonotif.py" ]
