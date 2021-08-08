#!/usr/bin/env python

import argparse
import gitlab
import googleapiclient.discovery
import json
import os
import time
from typing import Dict, Optional, Text, Union


class CMLDeployment:

    def __init__(
            self,
            gcp_project: Text,
            gcp_zone: Text,
            gcp_machine_name: Text,
            gcp_machine_type: Text,

            gitlab_access_token: Text,
            gitlab_project_id: Union[int, Text],
            gitlab_runner_name: Text,
            gitlab_runner_tags: Text,

            gcp_bucket: Optional[Text] = None,
            gcp_bucket_mount_path: Optional[Text] = None,

            gitlab_runner_default_image: Optional[Text] = None,
            gitlab_runner_volumes: Optional[Text] = None
    ) -> None:

        self.gcp_project = gcp_project
        self.gcp_zone = gcp_zone
        self.gcp_machine_name = gcp_machine_name
        self.gcp_machine_type = gcp_machine_type
        self.gcp_bucket = gcp_bucket
        self.gcp_bucket_mount_path = gcp_bucket_mount_path

        self.gitlab_access_token = gitlab_access_token
        self.gitlab_project_id = gitlab_project_id
        self.gitlab_runner_name = gitlab_runner_name
        self.gitlab_runner_tags = gitlab_runner_tags
        self.gitlab_runner_default_image = gitlab_runner_default_image
        self.gitlab_runner_volumes = gitlab_runner_volumes

        self.compute = googleapiclient.discovery.build('compute', 'v1')

    def deploy(self) -> None:

        instances = self._list_instances()
        # If instance with specified name does not exist then create it
        if self.gcp_machine_name not in instances:
            print('Creating instance.')
            operation = self._create_instance()
            self._wait_for_operation(operation['name'])
        else:
            print('Starting instance.')
            # Check if the instance is stopped. If yes - run it
            instance_status = instances[self.gcp_machine_name]['status']

            if instance_status == 'TERMINATED':
                operation = self._start_instance()
                self._wait_for_operation(operation['name'])

        instances = self._list_instances()

        for name, params in instances.items():
            print(f'{name}:{params["status"]}')

    def _list_instances(self) -> Dict[Text, Dict]:

        result = self.compute.instances().list(
            project=self.gcp_project, zone=self.gcp_zone
        ).execute()
        instances = {}

        if 'items' in result:

            for item in result['items']:
                instance_name = item.pop('name')
                instances[instance_name] = item

        return instances

    def _build_startup_script(self) -> Text:

        registration_token = self._gitlab_runner_reg_token()

        header = '#!/bin/sh'
        settings = '''
        export DEBIAN_FRONTEND=noninteractive
        echo "APT::Get::Assume-Yes \"true\";" | sudo tee -a /etc/apt/apt.conf.d/90assumeyes
        '''
        install_docker = '''
        echo "Install Docker"
        sudo curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
        sudo usermod -aG docker ubuntu
        sudo chmod 666 /var/run/docker.sock
        '''
        install_gitlab_runner = '''
        echo "Install GitLab runner"
        curl -LJO "https://gitlab-runner-downloads.s3.amazonaws.com/latest/deb/gitlab-runner_amd64.deb"
        yes | sudo dpkg -i gitlab-runner_amd64.deb
        '''
        register_gitlab_runner = f'''
            # Unregister old 
            gitlab-runner unregister --name {self.gitlab_runner_name}

            gitlab-runner register \\
                --non-interactive \\
                --name={self.gitlab_runner_name} \\
                -u https://gitlab.com/ \\
                -r {registration_token} \\
                --tag-list {self.gitlab_runner_tags} \\
                --executor docker \\
                --docker-devices /dev/fuse \\
                --docker-privileged '''

        if self.gitlab_runner_default_image:
            register_gitlab_runner += f'\\ --docker-image {self.gitlab_runner_default_image} '

        if self.gitlab_runner_volumes:
            for volume in self.gitlab_runner_volumes.split(','):
                register_gitlab_runner += f'''\
                --docker-volumes {volume} '''

        install_gcsfuse = '''
        export GCSFUSE_REPO=gcsfuse-`lsb_release -c -s`
        echo "deb http://packages.cloud.google.com/apt $GCSFUSE_REPO main" | sudo tee /etc/apt/sources.list.d/gcsfuse.list
        curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -

        sudo apt-get update
        sudo apt-get install -y gcsfuse
        '''

        mount_bucket = ''

        if self.gcp_bucket and self.gcp_bucket_mount_path:
            mount_bucket = f'''
            sudo mkdir -p {self.gcp_bucket_mount_path}
            sudo gcsfuse {self.gcp_bucket} {self.gcp_bucket_mount_path}
            '''

        run_runner = 'sudo gitlab-runner run'

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

    def _create_instance(self) -> object:
        # Get ubuntu image
        image_response = self.compute.images().getFromFamily(
            project='ubuntu-os-cloud', family='ubuntu-2004-lts'
        ).execute()
        source_disk_image = image_response['selfLink']
        # Configure the machine
        machine_type = f'zones/{self.gcp_zone}/machineTypes/{self.gcp_machine_type}'
        startup_script = self._build_startup_script()
        config = {
            'name': self.gcp_machine_name,
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
            'metadata': {
                'items': [
                    {
                        # Startup script is automatically executed by the
                        # instance upon startup.
                        'key': 'startup-script',
                        'value': startup_script
                    }
                ]
            }
        }

        return self.compute.instances().insert(
            project=self.gcp_project,
            zone=self.gcp_zone,
            body=config
        ).execute()

    def _start_instance(self) -> object:
        return self.compute.instances().start(
            project=self.gcp_project,
            zone=self.gcp_zone,
            instance=self.gcp_machine_name
        ).execute()

    def _wait_for_operation(self, operation_name: Text) -> None:

        print('Waiting for operation to finish...')

        while True:

            result = self.compute.zoneOperations().get(
                project=self.gcp_project,
                zone=self.gcp_zone,
                operation=operation_name
            ).execute()

            if result['status'] == 'DONE':

                print("done.")

                if 'error' in result:
                    raise Exception(result['error'])

                return result

            time.sleep(1)

    def _gitlab_runner_reg_token(self):

        gl = gitlab.Gitlab('https://gitlab.com', private_token=self.gitlab_access_token)
        gl.auth()
        project = gl.projects.get(self.gitlab_project_id)

        return project.attributes['runners_token']


def get_parser():

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
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

    required_env_vars = [
        'GOOGLE_APPLICATION_CREDENTIALS',
        'repo_token'
    ]

    for env_var in required_env_vars:
        if not os.getenv(env_var):
            raise EnvironmentError(f'Environment variable {env_var} not defined')

    with open(os.getenv('GOOGLE_APPLICATION_CREDENTIALS')) as gac_f:
        gac = json.load(gac_f)

    gcp_project = gac['project_id']

    cml_deployment = CMLDeployment(
        gcp_project=gcp_project,
        gcp_zone=args.gcp_zone,
        gcp_machine_name=args.gcp_machine_name,
        gcp_machine_type=args.gcp_machine_type,
        gcp_bucket=args.gcp_bucket,
        gcp_bucket_mount_path=args.gcp_bucket_mount_path,
        gitlab_access_token=args.gitlab_access_token,
        gitlab_project_id=args.gitlab_project_id,
        gitlab_runner_name=args.gitlab_runner_name,
        gitlab_runner_tags=args.gitlab_runner_tags,
        gitlab_runner_default_image=args.gitlab_runner_default_image,
        gitlab_runner_volumes=args.gitlab_runner_volumes
    )

    cml_deployment.deploy()


if __name__ == '__main__':
    main()
