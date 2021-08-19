#!/usr/bin/env python

import argparse
import gitlab
import googleapiclient.discovery
import json
import os
import time
from typing import Dict, Optional, Text, Union


class GCEInstance:

    def __init__(
            self,
            project: Text,
            zone: Text,
            machine_name: Text,
            machine_type: Text,
            bucket: Optional[Text] = None,
            bucket_mount_path: Optional[Text] = None,
            startup_script: Optional[Text] = None

    ) -> None:

        self.project = project
        self.zone = zone
        self.machine_name = machine_name
        self.machine_type = machine_type
        self.bucket = bucket
        self.bucket_mount_path = bucket_mount_path
        self.startup_script = startup_script

        self.compute = googleapiclient.discovery.build('compute', 'v1')
        # TODO: add statuses Enum
        self.status = None

        self._get_status()

    def create(self) -> object:
        # Get ubuntu image
        image_response = self.compute.images().getFromFamily(
            project='ubuntu-os-cloud', family='ubuntu-2004-lts'
        ).execute()
        source_disk_image = image_response['selfLink']
        # Configure the machine
        machine_type = f'zones/{self.zone}/machineTypes/{self.machine_type}'
        metadata_items = []

        if self.startup_script:
            metadata_items.append({
                # Startup script is automatically executed by the
                # instance upon startup.
                'key': 'startup-script',
                'value': self.startup_script
            })

        config = {
            'name': self.machine_name,
            'machineType': machine_type,

            # Specify the boot disk and the image to use as a source.
            'disks': [
                {
                    'boot': True,
                    'autoDelete': True,
                    'initializeParams': {
                        'sourceImage': source_disk_image,
                    }
                }
            ],
            # Specify a network interface with NAT to access the public
            # internet.
            'networkInterfaces': [{
                'network': 'global/networks/default',
                'accessConfigs': [
                    {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
                ]
            }],
            # Allow the instance to access cloud storage and logging.
            'serviceAccounts': [{
                'email': 'default',
                # Allow full access to all APIs
                'scopes': ['https://www.googleapis.com/auth/cloud-platform']
            }],
            # Metadata is readable from the instance and allows you to
            # pass configuration from deployment scripts to instances.
            'metadata': {'items': metadata_items}
        }

        return self.compute.instances().insert(
            project=self.project,
            zone=self.zone,
            body=config
        ).execute()

    def start(self) -> object:
        return self.compute.instances().start(
            project=self.project,
            zone=self.zone,
            instance=self.machine_name
        ).execute()

    def stop(self) -> object:
        return self.compute.instances().stop(
            project=self.project,
            zone=self.zone,
            instance=self.machine_name
        ).execute()

    def delete(self) -> object:
        return self.compute.instances().delete(
            project=self.project,
            zone=self.zone,
            instance=self.machine_name
        ).execute()

    def wait_for_operation(self, operation_name: Text) -> None:

        print('Waiting for operation to finish...')

        while True:

            result = self.compute.zoneOperations().get(
                project=self.project,
                zone=self.zone,
                operation=operation_name
            ).execute()

            if result['status'] == 'DONE':

                print("done.")

                if 'error' in result:
                    raise Exception(result['error'])

                return result

            time.sleep(1)

    def exists(self) -> bool:

        if self.status in ['RUNNING', 'TERMINATED']:
            return True

        return False

    def set_startup_script(self, startup_script) -> None:
        self.startup_script = startup_script

    def _get_status(self) -> None:

        instances = self._list_instances()
        # If instance with specified name does not exist then create it
        if self.machine_name not in instances:
            self.status = 'NONEXISTENT'
        else:
            # Check if the instance is stopped. If yes - run it
            self.status = instances[self.machine_name]['status']

    def _list_instances(self) -> Dict[Text, Dict]:

        result = self.compute.instances().list(
            project=self.project, zone=self.zone
        ).execute()
        instances = {}

        if 'items' in result:

            for item in result['items']:
                instance_name = item.pop('name')
                instances[instance_name] = item

        return instances


class GitlabRunner:

    def __init__(
            self,
            access_token: Text,
            project_id: Union[int, Text],
            name: Text,
            tags: Text,
            default_image: Optional[Text] = None,
            volumes: Optional[Text] = None

    ) -> None:

        self.access_token = access_token
        self.project_id = project_id
        self.name = name
        self.tags = tags
        self.default_image = default_image
        self.volumes = volumes

    def registration_command(self) -> Text:

        reg_token = self._registration_token()

        register_gitlab_runner = f'''
        # Verify runner
        sudo gitlab-runner verify --name {self.name}

        if  [ $? -ne 0 ]; then
            # Unregister old 
            gitlab-runner unregister --name {self.name}

            gitlab-runner register \
                --non-interactive \
                --name={self.name} \
                -u https://gitlab.com/ \
                -r {reg_token} \
                --tag-list {self.tags} \
                --executor docker \
                --docker-devices /dev/fuse \
                --docker-privileged '''

        if self.default_image:
            register_gitlab_runner += f'''\
            --docker-image {self.default_image} '''

        if self.volumes:
            for volume in self.volumes.split(','):
                register_gitlab_runner += f'''\
                --docker-volumes {volume} '''

        register_gitlab_runner += f'''
        fi
        '''

        return register_gitlab_runner

    def _registration_token(self):

        gl = gitlab.Gitlab('https://gitlab.com', private_token=self.access_token)
        gl.auth()
        project = gl.projects.get(self.project_id)

        return project.attributes['runners_token']


class CMLDeployment:

    def __init__(
            self,
            instance: GCEInstance,
            runner: GitlabRunner
    ) -> None:

        self.instance = instance
        self.runner = runner

    def deploy(self) -> None:

        # If instance with specified name does not exist then create it
        if not self.instance.exists():

            print('Creating instance.')
            startup_script = self._build_startup_script()
            self.instance.set_startup_script(startup_script)
            operation = self.instance.create()
            self.instance.wait_for_operation(operation['name'])

        else:

            print('Starting instance.')

            if self.instance.status == 'TERMINATED':
                operation = self.instance.start()
                self.instance.wait_for_operation(operation['name'])

    def _build_startup_script(self) -> Text:

        header = '#!/bin/sh'
        settings = '''
        export DEBIAN_FRONTEND=noninteractive
        echo "APT::Get::Assume-Yes \"true\";" | sudo tee -a /etc/apt/apt.conf.d/90assumeyes
        '''
        install_docker = '''
        if ! which docker > /dev/null; then
            echo "Install Docker"
            sudo curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
            sudo usermod -aG docker ubuntu
            sudo chmod 666 /var/run/docker.sock
        fi
        '''
        install_gitlab_runner = '''
        if ! which gitlab-runner > /dev/null; then
            echo "Install GitLab runner"
            curl -LJO "https://gitlab-runner-downloads.s3.amazonaws.com/latest/deb/gitlab-runner_amd64.deb"
            yes | sudo dpkg -i gitlab-runner_amd64.deb
        fi
        '''
        register_gitlab_runner = self.runner.registration_command()

        install_gcsfuse = '''
        if ! which gcsfuse > /dev/null; then
            export GCSFUSE_REPO=gcsfuse-`lsb_release -c -s`
            echo "deb http://packages.cloud.google.com/apt $GCSFUSE_REPO main" | sudo tee /etc/apt/sources.list.d/gcsfuse.list
            curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -

            sudo apt-get update
            sudo apt-get install -y gcsfuse
        fi
        '''

        mount_bucket = ''
        bucket = self.instance.bucket
        mount_path = self.instance.bucket_mount_path

        if bucket and mount_path:
            mount_bucket = f'''
            sudo mkdir -p {mount_path}
            sudo gcsfuse {bucket} {mount_path} '''

        run_runner = '''
        sudo gitlab-runner status

        if  [ $? -ne 0 ]; then
            sudo gitlab-runner start
        fi
        '''

        startup_script = f'''
        {header}

        {settings}

        {install_docker}

        {install_gitlab_runner}

        {register_gitlab_runner}

        {install_gcsfuse}

        {mount_bucket}

        {run_runner}
        '''

        return startup_script


def get_parser():

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('action', choices=['deploy', 'stop', 'delete'])
    parser.add_argument(
        '--gcp-zone',
        dest='gcp_zone',
        default='us-west1-b',
        help='Compute Engine zone to deploy to.'
    )
    parser.add_argument(
        '--gcp-machine-name',
        dest='gcp_machine_name',
        default='cml-vm',
        help='New instance name.'
    )
    parser.add_argument(
        '--gcp-machine-type',
        dest='gcp_machine_type',
        default='f1-micro',
        help='Compute Engine machine type'
    )
    parser.add_argument(
        '--gcp-bucket',
        dest='gcp_bucket',
        default=None,
        help='Bucket name to mount on volume.'
    )
    parser.add_argument(
        '--gcp-bucket-mount-path',
        dest='gcp_bucket_mount_path',
        default=None,
        help='Path to mount bucket.'
    )
    parser.add_argument(
        '--gitlab-access-token',
        dest='gitlab_access_token',
        default=os.getenv('repo_token'),
        help='Gitlab personal access token.'
    )
    parser.add_argument(
        '--gitlab-project-id',
        dest='gitlab_project_id',
        default=os.getenv('CI_PROJECT_ID'),
        help='Gitlab personal access token.'
    )
    parser.add_argument(
        '--gitlab-runner-name',
        dest='gitlab_runner_name',
        default='cml-runner',
        help='Gitlab runner name.'
    )
    parser.add_argument(
        '--gitlab-runner-tags',
        dest='gitlab_runner_tags',
        default='cml-runner',
        help='Gitlab runner tags list.'
    )
    parser.add_argument(
        '--gitlab-runner-default-image',
        dest='gitlab_runner_default_image',
        default='dvcorg/cml:latest',
        help='Gitlab runner default docker image.'
    )
    parser.add_argument(
        '--gitlab-runner-volumes',
        dest='gitlab_runner_volumes',
        default=None,
        help='Gitlab runner default docker volumes.'
    )

    return parser


def main():

    args_parser = get_parser()
    args = args_parser.parse_args()

    if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
        raise EnvironmentError(f'Environment variable GOOGLE_APPLICATION_CREDENTIALS not defined')

    with open(os.getenv('GOOGLE_APPLICATION_CREDENTIALS')) as gac_f:
        gac = json.load(gac_f)

    gcp_project = gac['project_id']

    instance = GCEInstance(
        project=gcp_project,
        zone=args.gcp_zone,
        machine_name=args.gcp_machine_name,
        machine_type=args.gcp_machine_type,
        bucket=args.gcp_bucket,
        bucket_mount_path=args.gcp_bucket_mount_path
    )

    if args.action == 'deploy':
        runner = GitlabRunner(
            access_token=args.gitlab_access_token,
            project_id=args.gitlab_project_id,
            name=args.gitlab_runner_name,
            tags=args.gitlab_runner_tags,
            default_image=args.gitlab_runner_default_image,
            volumes=args.gitlab_runner_volumes
        )
        cml_deployment = CMLDeployment(instance=instance, runner=runner)
        cml_deployment.deploy()

    elif args.action == 'stop':
        instance.stop()

    elif args.action == 'delete':
        instance.delete()

    else:
        raise ValueError(f'Invalid action {args.action}')


if __name__ == '__main__':
    main()
