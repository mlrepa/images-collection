FROM python:3.8-slim

COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache -r ./requirements.txt

COPY deploy.py /usr/bin/deploy
RUN chmod +x /usr/bin/deploy

ENTRYPOINT ["/bin/bash"]