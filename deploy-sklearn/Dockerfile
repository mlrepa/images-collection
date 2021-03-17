FROM python:3.7-slim

RUN apt-get update && \
    apt-get install -y curl git sudo && \
    useradd -m user -u 1000 && \
    echo 'user:user' | chpasswd user && \
    echo "user ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/user && \
    chmod 0440 /etc/sudoers.d/user && \
    chown -R user /home && \
    rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

WORKDIR /home/deploy

USER user

COPY app.py /home/deploy/app.py
CMD python /home/deploy/app.py
