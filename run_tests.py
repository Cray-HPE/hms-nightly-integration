#! /usr/bin/env python3

# MIT License
#
# (C) Copyright [2023] Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
import os
import sys
import json
import subprocess
import yaml
import docker
import tarfile
import re

# TODO switch to arg parse
images_by_csm_release = sys.argv[1]
csm_release = sys.argv[2]

docker_client = docker.from_env()


#
# Detect tests
#

# Read in the json file created by the csm_manifest_extractor.py
images_by_csm_release = None
with open(sys.argv[1], 'r') as f:
    images_by_csm_release = json.load(f)

if csm_release not in images_by_csm_release:
    print(f'Error provided CSM release does not exist in {sys.argv[1]}')
    exit(1)

images = images_by_csm_release[csm_release]

legacy_ct_images = []
hmth_images = []
for image_repo in images:
    image = f'{image_repo}:{images[image_repo][0]}'
    if image_repo.endswith("hmth-test"):
        # This is a HMTH test
        print(f'Found HMTH test image: {image}')
        hmth_images.append(image)
    elif image_repo.endswith("test"):
        # This is a legacy HMS CT test
        print(f'Found Legacy CT test image: {image}')
        legacy_ct_images.append(image)


tests_to_run = []

# Pull required images
for image in legacy_ct_images + hmth_images:
    print("Pulling", image)
    docker_client.images.pull(image)

# Inspect each container image to learn what tests it supports
def list_image_files(docker_client: docker.DockerClient, image: str) -> list[str]:
    # Inspect the container image, without actually running it to determine if this this is a valid image
    container = docker_client.containers.create(image)
    # print(container.id)
    # print(container.name)

    result = subprocess.run(f'docker export {container.name} | tar -t', shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print("Failed to extract files fron container. Exit code {}".format(result.returncode))
        print("stderr: {}".format(result.stderr))
        print("stdout: {}".format(result.stdout))
        exit(1)

    container.remove()

    return result.stdout.splitlines()

tests = {}


def detect_tests(images, test_type, wanted_tests):
    global tests


    if test_type not in tests:
        tests[test_type] = {}

    for image in images:
        print(f'Detecting {test_type} tests in {image}')

        for file in list_image_files(docker_client, image):
            if file in wanted_tests:
                test_class = wanted_tests[file]
                if test_class not in tests[test_type]:
                    tests[test_type][test_class] = []

                tests[test_type][test_class].append(image)

detect_tests(legacy_ct_images, "legacy_ct", wanted_tests = {
    "src/app/smoke_test.py": "smoke",
    "src/app/functional_test.py": "functional"
})

detect_tests(hmth_images, "hmth", wanted_tests = {
    "src/app/smoke.json": "smoke",
    "src/app/api/1-non-disruptive/": "1-non-disruptive",
    "src/app/api/2-disruptive/": "2-disruptive",
    "src/app/api/3-destructive/": "3-destructive",
    "src/app/api/4-build-pipeline-only/": "4-build-pipeline-only"
})

with open('image_tests.json', 'w') as f:
    json.dump(tests, f, indent=2)

#
# Run tests from least to most destructive
#

test_order = [
    ("legacy_ct", "smoke"),
    ("hmth", "smoke"),
    ("legacy_ct", "functional"),
    ("hmth", "1-non-disruptive"),
    # ("hmth", "2-disruptive"),
    # TODO thing about these two cases
    # ("hmth", "3-destructive"),
    # ("hmth", "4-build-pipeline-only"),
]

smoke_host_override = {
    # SLS
    "artifactory.algol60.net/csm-docker/stable/cray-sls-test":      "http://cray-sls:8376",
    "artifactory.algol60.net/csm-docker/stable/cray-sls-hmth-test": "http://cray-sls:8376",

    # HSM
    "artifactory.algol60.net/csm-docker/stable/cray-smd-test":      "http://cray-smd:27779",
    "artifactory.algol60.net/csm-docker/stable/cray-smd-hmth-test": "http://cray-smd:27779",

    # CAPMC
    "artifactory.algol60.net/csm-docker/stable/cray-capmc-test":      "http://cray-capmc:27777",
    "artifactory.algol60.net/csm-docker/stable/cray-capmc-hmth-test": "http://cray-capmc:27777",

    # PCS
    "artifactory.algol60.net/csm-docker/stable/cray-power-control-test":      "http://cray-power-control:28007",
    "artifactory.algol60.net/csm-docker/stable/cray-power-control-hmth-test": "http://cray-power-control:28007",

    # REDS
    "artifactory.algol60.net/csm-docker/stable/cray-reds-test":      "http://cray-reds:8269",
    "artifactory.algol60.net/csm-docker/stable/cray-reds-hmth-test": "http://cray-reds:8269",

    # BSS
    "artifactory.algol60.net/csm-docker/stable/cray-bss-test":      "http://cray-bss:27778",
    "artifactory.algol60.net/csm-docker/stable/cray-bss-hmth-test": "http://cray-bss:27778",

    # FAS
    "artifactory.algol60.net/csm-docker/stable/cray-firmware-action-test":      "http://cray-fas:28800",
    "artifactory.algol60.net/csm-docker/stable/cray-firmware-action-hmth-test": "http://cray-fas:28800",

    # HBTD
    "artifactory.algol60.net/csm-docker/stable/cray-hbtd-test":      "http://cray-hbtd:28500",
    "artifactory.algol60.net/csm-docker/stable/cray-hbtd-hmth-test": "http://cray-hbtd:28500",

    # HMNFD
    "artifactory.algol60.net/csm-docker/stable/cray-hmnfd-test":      "http://cray-hmnfd:28600",
    "artifactory.algol60.net/csm-docker/stable/cray-hmnfd-hmth-test": "http://cray-hmnfd:28600"
}

for test_type, test_class in test_order:
    print("========================================")
    print(f'Running {test_type}:{test_class} tests')
    print("========================================")

    if test_type not in tests:
        print(f'Skipping! No tests with type "{test_type}" detected')
        continue

    if test_class not in tests[test_type]:
        print(f'Skipping! No tests with class "{test_class}" detected')
        continue

    for image in tests[test_type][test_class]:
        print(f'Running {image}')

        cmd = None

        if test_type in ["hmth", "legacy_ct"] and test_class == "smoke":
            image_repo, image_tag = image.split(":", 2)
                        
            cmd = ["docker", "run", "--rm", "-it", "--network", "hms-simulation-environment_simulation", image, "smoke", "-f", "smoke.json"]
            if image_repo in smoke_host_override:
                cmd = cmd + ["-u", smoke_host_override[image_repo]]
        elif test_type == "legacy_ct" and test_class == "functional":
            cmd = ["docker", "run", "--rm", "-it", "--network", "hms-simulation-environment_simulation", image, "functional", "-c", "/src/app/tavern_global_config_ct_test.yaml", "-p", '/src/app']
        elif test_type == "hmth":
            # Note there are two tavern configuration files, one from the application repo, and one from HMS test. They have different endpoints defined
            # - Application Repo: /src/app/tavern_global_config_ct_test.yaml
            # - HMS Test: /src/libs/tavern_global_config.yaml
            cmd = ["docker", "run", "--rm", "-it", "--network", "hms-simulation-environment_simulation", image, "tavern", "-c", "/src/app/tavern_global_config_ct_test.yaml", "-p", f'/src/app/api/{test_class}']
        else:
            print(f'Unknown test type {test_type}:{test_class}')

        if cmd is None:
            print("Skipping unsupported test")
            continue

        print("Command", cmd)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # TODO better message
            print("Tests failed. Exit code {}".format(result.returncode))
            print("stderr: {}".format(result.stderr))
            print("stdout: {}".format(result.stdout))
            continue

        print(result.stdout)