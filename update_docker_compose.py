#! /usr/bin/env python3

import argparse
import os
import sys
import json
import subprocess
import yaml

# TODO expand to use data from test_global_config.yaml

# Parse CLI arguments
parser = argparse.ArgumentParser()
parser.add_argument("--csm-extractor-output-json", type=str, default="csm-manifest-extractor-output.json", help="Read in the json file created by the csm_manifest_extractor.py")
parser.add_argument("--csm-release", type=str, default="main", help="CSM release branch to target")
parser.add_argument("--docker-compose-file", type=str, default="./hms-simulation-environment/docker-compose.yaml", help="Path to the HMS Simulation Environment docker-compose.yaml file to update")

args = parser.parse_args()

# Read in the json file created by the csm_manifest_extractor.py
csm_extractor_output = None
with open(args.csm_extractor_output_json, 'r') as f:
    csm_extractor_output = json.load(f)

if args.csm_release not in csm_extractor_output:
    print(f'Error provided CSM release does not exist in {args.csm_extractor_output_json}')
    exit(1)

image_overrides = csm_extractor_output[args.csm_release]["images"]

# Read in the docker-compose file
docker_compose = None
with open(args.docker_compose_file, 'r') as f:
    docker_compose = yaml.safe_load(f)

# Loop through services looking images
for service_name in docker_compose["services"]:
    service = docker_compose["services"][service_name]

    if "image" not in service:
        print(f'Skipping service {service_name} due to missing "image" field')
        continue

    image_repo, image_tag = service["image"].split(":", 2)

    if image_repo in image_overrides:
        # HACK we are assuming that one image is present in a CSM release.
        # If there are more then one, we are just using the first one
        image_override = f'{image_repo}:{image_overrides[image_repo][0]}'
        print(f'Overriding service {service_name} image with {image_override}')

        cmd = ['yq', '-i', 'e', f'.services.{service_name}.image = "{image_override}"', args.docker_compose_file]
        print(f'Running command: {cmd}')
        result = subprocess.run(cmd)
        if result.returncode != 0:
            sys.exit(1)