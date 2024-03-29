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
import argparse
import os
import github
import semver
import json
import yaml
import docker



if __name__ == "__main__":
    #
    # Parse CLI arguments
    #
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-config-global", type=str, default="test_config_global.yaml",  help="Global test configuration file")

    args = parser.parse_args()

    #
    # Load configuration
    #
    github_token = os.getenv("GITHUB_TOKEN")

    # Docker client
    docker_client = docker.from_env()

    # Global test config
    test_config_global = None
    with open(args.test_config_global, 'r') as f:
        test_config_global = yaml.safe_load(f)

    # Identity git repos of interest
    github_repos = []
    repo_application_image_lookup = {}
    repo_test_image_lookup = {}
    for service in test_config_global["services"].values():
        github_repo = service["github"]["repo"]["application"]
        github_repos.append(github_repo)

        repo_application_image_lookup[github_repo] = service["image"]["repo"]["application"]["stable"]
        repo_test_image_lookup[github_repo] = service["image"]["repo"]["test"]["stable"]


    g = github.Github(github_token)
    latest_images = {}
    for github_repo in github_repos:
        print(f'Processing repo Cray-HPE/{github_repo}')
        repo = g.get_organization("Cray-HPE").get_repo(github_repo)
        versions = []
        for tag in repo.get_tags():
            # Ignore non-version strings
            if not tag.name.startswith("v"):
                continue

            print(f'  Found tag: {tag.name}')
            
            # Remove tag prefix
            version_string = tag.name.removeprefix("v")

            try:
                # Parse the string to see if its valid semver
                version = semver.VersionInfo.parse(version_string)

                # Ignore prerelease tags
                if version.prerelease:
                    print(f'  Skipping prerelease tag: {version_string}')
                    continue
                
                versions.append(version)

            except ValueError as e:
                print(f'  Unable to parse version string {version_string}: {e}')
                continue
        
        # Determine latest tags
        versions.sort(reverse=True)
        latest_version = versions[0]
        print(f'  Latest version: {latest_version}')

        # Application image
        latest_application_image = f'{repo_application_image_lookup[github_repo]}:{latest_version}'
        latest_images[repo_application_image_lookup[github_repo]] = [str(latest_version)]
        print(f'  Latest application image: {latest_application_image}')

        # Test image
        latest_test_image = f'{repo_test_image_lookup[github_repo]}:{latest_version}'
        print(f'  Latest test image: {latest_test_image}')

        # Determine if the test image exists in Artifactory
        try:
            docker_client.images.get_registry_data(latest_test_image)
            latest_images[repo_test_image_lookup[github_repo]] = [str(latest_version)]
        except docker.errors.NotFound as e:
            print(f'  Test image does not exist: {e}')

    # Build output that is comparable with the csm-manifest-extractor.py
    output = {
        "bleeding-edge": {
            "images": latest_images,
            "git_sha": None,
            "git_tags": []
        }
    }

    with open("bleeding-edge-image-versions.json", 'w') as f:
        json.dump(output, f, indent=2)