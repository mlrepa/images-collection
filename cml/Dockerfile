FROM dvcorg/cml:latest

COPY ./requirements.txt ./requirements.txt

RUN  pip install --upgrade pip setuptools wheel && \
     pip install --no-cache -r requirements.txt