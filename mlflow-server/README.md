# Description

Simple mlflow server


# Build

```bash
docker build -t mlrepa/mlflow-server:dev .
```


# Create network
```bash
docker network create mlflow-server
```

# Run

Example:

```bash
export PORT=1234
export BACKEND_STORE=postgresql+psycopg2://postgres:postgres@postgres:5432/postgres
export ARTIFACT_ROOT=$PWD/mlflow_ws

# up server
docker run \
        --name=mlflow-server \
        -p $PORT:$PORT \
        --expose $PORT \
        --network=mlflow-server \
        --rm \
        -e PORT=$PORT \
        -e BACKEND_STORE=$BACKEND_STORE \
        -e ARTIFACT_ROOT=$ARTIFACT_ROOT \
        [-v $ARTIFACT_ROOT:$ARTIFACT_ROOT] \  # if ARTIFACT_ROOT is local folder
        mlrepa/mlflow-server:dev
```


# Stop

```bash
docker stop mlflow-server
```

# Usage examples

## from host

```python
import mlflow

mlflow.set_tracking_uri('http://0.0.0.0:1234')

with mlflow.start_run(): 
   mlflow.log_param('p', 12) 
   mlflow.log_artifact('mymodel.joblib') 
```

## from docker

run you docker application:

```bash
docker run \
        --name=<your_container> \
        -v $ARTIFACT_ROOT:$ARTIFACT_ROOT \
        --network=mlflow-server <your_image>
```

enter container:

```bash
docker exec -ti <your_container> /bin/bash 
```

python code:

```python
import mlflow

mlflow.set_tracking_uri('http://mlflow-server:1234')

with mlflow.start_run(): 
   mlflow.log_param('p', 12) 
   mlflow.log_artifact('mymodel.joblib')
```