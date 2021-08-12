# cml deploy

Create GCE instance and deploy gitlab-runner on it

## Description

Docker image `mlrepa/cml-deploy` includes script `deploy` which allows to create and provision 
GCE instances.

Deploy script does the next:
- creates GCE instance
- installs software required for ML flows (docker, gitlab-runner, gcsfuse and so on)
- mounts bucket to instance (optional)
- registers and runs gitlab runner

## Build docker image

```bash
docker build -t mlrepa/cml-deploy:latest .
```

## Environment variables

Deploy script deals with Google Compute API therefore it requires environment variable  
`GOOGLE_APPLICATION_CREDENTIALS` to be defined.

Some parameters of deploy script take default values from environment variables: 

| Parameter | Variable name  | Description |
|---|---|---|
| --gitlab-access-token | repo_token | GitLab personal access token |
| --gitlab-project-id |  CI_PROJECT_ID | GitLab project id for which the runner is creating |


## Deploy script usage

```bash
$ deploy --help
usage: deploy [-h] [--gcp-zone GCP_ZONE] [--gcp-machine-name GCP_MACHINE_NAME] [--gcp-machine-type GCP_MACHINE_TYPE] [--gcp-bucket GCP_BUCKET] [--gcp-bucket-mount-path GCP_BUCKET_MOUNT_PATH]
              [--gitlab-access-token GITLAB_ACCESS_TOKEN] [--gitlab-project-id GITLAB_PROJECT_ID] [--gitlab-runner-name GITLAB_RUNNER_NAME] [--gitlab-runner-tags GITLAB_RUNNER_TAGS]
              [--gitlab-runner-default-image GITLAB_RUNNER_DEFAULT_IMAGE] [--gitlab-runner-volumes GITLAB_RUNNER_VOLUMES]

optional arguments:
  -h, --help            show this help message and exit
  --gcp-zone GCP_ZONE   Compute Engine zone to deploy to.
  --gcp-machine-name GCP_MACHINE_NAME
                        New instance name.
  --gcp-machine-type GCP_MACHINE_TYPE
                        Compute Engine machine type
  --gcp-bucket GCP_BUCKET
                        Bucket name to mount on volume.
  --gcp-bucket-mount-path GCP_BUCKET_MOUNT_PATH
                        Path to mount bucket.
  --gitlab-access-token GITLAB_ACCESS_TOKEN
                        Gitlab personal access token.
  --gitlab-project-id GITLAB_PROJECT_ID
                        Gitlab personal access token.
  --gitlab-runner-name GITLAB_RUNNER_NAME
                        Gitlab runner name.
  --gitlab-runner-tags GITLAB_RUNNER_TAGS
                        Gitlab runner tags list.
  --gitlab-runner-default-image GITLAB_RUNNER_DEFAULT_IMAGE
                        Gitlab runner default docker image.
  --gitlab-runner-volumes GITLAB_RUNNER_VOLUMES
                        Gitlab runner default docker volumes.

```

## Usage examples

### Deploy manually

1. run container with mounting Google application credentials json

```bash
docker run \
  -ti \
  -v <GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH>:<GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH> \
  -e GOOGLE_APPLICATION_CREDENTIALS=<GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH> \
  -e repo_token=<gitlab_personal_access_token> \
  -e CI_PROJECT_ID=<gitlab_project_id> \
    mlrepa/cml-deploy:latest /bin/bash
    
```

2. run deploy command inside container

```bash
deploy \
    --gcp-machine-type=g1-small \
    --gcp-machine-name=cml-vm \
    --gitlab-runner-name=cml-runner \
    --gitlab-runner-tags=cml-runner \
    --gitlab-runner-volumes="/tmp:/tmp,/home/bucket_mount_path:/home/bucket_mount_path" \
    --gcp-bucket="bucket" \
    --gcp-bucket-mount-path=/home/bucket_mount_path
```

### Deploy from inside CI pipeline

1. define CI/CD Variables (**Settings** -> **CI/CD** -> **Variables**):

| Key  | Content | Variable type |
|---|---|---|
|  repo_token | Personal Access Token | Variable |
| GOOGLE_APPLICATION_CREDENTIALS  | Content of GCP json credentials specific for the project  | File |

2. define deploy job in CI pipeline:

`.gitlab-ci.yml`
```yaml
stages:
  - deploy
  - ...
  - ...

deploy_job:
  stage: deploy
  image: mlrepa/cml-deploy:latest
  script:
    - deploy
      --gcp-machine-type=g1-small
      --gcp-machine-name=cml-deploy
      --gitlab-runner-name=cml-runner
      --gitlab-runner-tags=cml-runner
      --gitlab-runner-volumes="/tmp:/tmp,/home/bucket_mount_path:/home/bucket_mount_path"
      --gcp-bucket="bucket"
      --gcp-bucket-mount-path=/home/bucket_mount_path
```

See demo [cml-deploy-example](https://gitlab.com/7labs.ru/research/cicd/dvc-studio/cml-deploy-example)