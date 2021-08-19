FROM python:3.8-slim

COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache -r ./requirements.txt

COPY cml-runner-gcp.py /usr/bin/cml-runner-gcp
RUN chmod +x /usr/bin/cml-runner-gcp
