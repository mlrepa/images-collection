FROM python:3.8-slim

RUN apt-get update && \
    apt-get install -y gcc curl build-essential

COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache -r ./requirements.txt

ENV HOME_DIR="/home"
WORKDIR ${HOME_DIR}

COPY start.sh start.sh
RUN chmod +x start.sh

USER 1000

CMD ./start.sh
