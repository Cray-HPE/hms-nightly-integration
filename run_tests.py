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
import docker
import json
import shutil
import pathlib
import os
import subprocess
import yaml
import multiprocessing as mp

# Inspect each container image to learn what tests it supports
def list_image_files(docker_client: docker.DockerClient, image: str) -> list[str]:
    # Inspect the container image, without actually running it to determine if this this is a valid image
    container = docker_client.containers.create(image)

    result = subprocess.run(f'docker export {container.name} | tar -t', shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print("Failed to extract files from container. Exit code {}".format(result.returncode))
        print("stderr: {}".format(result.stderr))
        print("stdout: {}".format(result.stdout))
        exit(1)

    container.remove()

    return result.stdout.splitlines()

def detect_test_classes(docker_client: docker.DockerClient, images: list[str], tests_dir: pathlib.Path, wanted_tests: dict, tavern_configs: dict):
    test_results = {}
    tavern_config_results = {}

    for image in images:
        print(f"Detecting tests in {image}")
        tavern_config_results[image] = []
        for file in list_image_files(docker_client, image):
            # Look for files that determine what tests are present
            if file in wanted_tests:
                print(f"  Found test file: {str(file)}")
                # We have a match!
                test_class = wanted_tests[file]
                if test_class not in test_results:
                    test_results[test_class] = []

                test_results[test_class].append(image)
            
            # Look for test configurations
            if file in tavern_configs:
                print(f"  Found tavern config file: {str(file)}")
                tavern_config_results[image].append(tavern_configs[str(file)])

    return test_results, tavern_config_results

def run_tests(test_global_test_config: dict, detected_tavern_configs, tests: list[dict], allure_report_dir: pathlib.Path):
    # Remove existing reports
    if allure_report_dir.exists():
        shutil.rmtree(allure_report_dir)

    # Generate tavern config
    # TODO change this to use the tavern config built into the container image
    tavern_config = test_config_global["tavern"].copy()
    for service in test_config_global["services"]:
        url = test_config_global["services"][service]["url"]["container"]

        tavern_config["variables"][f'{service.lower()}_base_url'] = url

    tavern_global_config_path = pathlib.Path('.').joinpath("tavern_global_config.yaml")

    with open(tavern_global_config_path, 'w') as f:
        yaml.dump(tavern_config, f)

    # Build up smoke test lookup map
    # TODO some stream lining could occur if a better structure was used for information regarding a test
    smoke_host_override = {}
    for service in test_global_test_config["services"].values():
        for image_repo in service["image"]["repo"]["test"].values():
            smoke_host_override[image_repo] = service["url"]["container"]

    print("Smoke test host overrides")
    print(json.dumps(smoke_host_override, indent=2))

    for test in tests:
        test_class = test["test_class"]

        print("========================================")
        print(f'Running {test["test_name"]} tests')
        print("========================================")
        
        for image in test["images"]:
            print(f'Running {image}')
            image_repo, image_tag = image.split(":", 2)
            short_name = os.path.basename(image_repo)

            test_args = []

            if test_class == "smoke":
                test_args = ["smoke", "--file", "smoke.json"]
                
                image_repo, image_tag = image.split(":", 2)
                if image_repo in smoke_host_override:
                    test_args = test_args + ['--url', smoke_host_override[image_repo]]
            else:
                # By default use the tavern config generated by this tool if none exist
                tavern_config = "/tavern_global_config.yaml"
                if "emulated_hardware" in detected_tavern_configs[image]:
                    tavern_config = "/src/app/tavern_global_config_ct_test_emulated_hardware.yaml"
                elif "default" in detected_tavern_configs[image]:
                    tavern_config = "/src/app/tavern_global_config_ct_test.yaml"

                # Test arguments
                test_args = ['tavern', '--config', tavern_config, '--path', f'/src/app/api/{test_class}']

            if test_args is None:
                print("Skipping unsupported test")
                continue

            cmd = ["docker", "run", "--rm", "-t", 
                "--network", "hms-simulation-environment_simulation",   # Connect to the simulation network 
                "-v", f'{str(allure_dir.absolute())}:/allure-results/', # Location to output the allure results
                "-v", f'{str(tavern_global_config_path.absolute())}:/tavern_global_config.yaml', # Tavern configuration
                "--user", "root"
            ] + [image] + test_args + [f'--allure-dir=/allure-results/{short_name}/{test_class}']

            print("Command:", ' '.join(cmd))

            result = subprocess.run(cmd)
            if result.returncode != 0:
                print("Tests failed. Exit code {}".format(result.returncode))
                continue

def process_allure_reports(allure_report_dir: pathlib.Path):
    for test_result_path in allure_report_dir.glob("**/*result.json"):
        test_source = test_result_path.parent.parent.name
        test_class = test_result_path.parent.name
        print(f'Processing test result: {str(test_result_path)}') 
        
        # Read in test result file
        test_result = None
        with open(test_result_path, 'r') as f:
            test_result = json.load(f)

        # Fix the suite name, and also add a parent suite. 
        # This will create an hierarchy of:
        # service_name:
        # -> smoke
        # -> 1-non-disruptive
        # -> 2-disruptive
        # etc...
        parent_suite_exists = False;
        for label in test_result["labels"]:
            if label["name"] == "suite":
                label["value"] = test_class
            elif label["name"] == "parentSuite":
                label["value"] = test_source
                parent_suite_exists = True

        if not parent_suite_exists:
            test_result["labels"].append({
                "name": "parentSuite",
                "value": test_source
            })

        # Hack: Change broken to failed.
        # Due to how tavern produced exceptions they show up as broken in allure
        if test_result["status"] == "broken":
            test_result["status"] = "failed"
        if "steps" in test_result:
            for step in test_result["steps"]:
                if step["status"] == "broken":
                    step["status"] = "failed"

        # Write the data back out
        with open(test_result_path, 'w') as f:
            json.dump(test_result, f, indent=2)

    # Move test reports into toplevel directory
    for file in allure_report_dir.glob("**/*"):
        if not file.is_file(): 
            continue
        destination = allure_report_dir / file.name
        print(f'Moving {str(file)} -> {str(destination)}')
        file.rename(destination)

if __name__ == "__main__":
    #
    # Parse CLI flags
    #
    parser = argparse.ArgumentParser()
    parser.add_argument("--csm-extractor-output-json", type=str, default="csm-manifest-extractor-output.json", help="Read in the json file created by the csm_manifest_extractor.py")
    parser.add_argument("--csm-release", type=str, default="main", help="CSM release branch to target")
    parser.add_argument("--test-config-global", type=str, default="test_config_global.yaml",  help="Global test configuration file")

    parser.add_argument("--allure-dir", type=str, default="./allure",  help="Allure output director")
    parser.add_argument("--fix-allure-dir-perms", type=bool, default=False, action=argparse.BooleanOptionalAction, help="Correct file permissions of allure test report files when running in github actions")
    parser.add_argument("--tests-output-dir", type=str, default="./tests",  help="Directory to store tests")
    
    parser.add_argument("--skip-pull", type=bool, default=False, action=argparse.BooleanOptionalAction, help="Skipping pulling of images. For local dev only")
    parser.add_argument("--skip-tests", type=bool, default=False, action=argparse.BooleanOptionalAction, help="Skipping running of tests. For local dev only")

    parser.add_argument("--github-action-id", type=str, default="", help="Github Action run ID")

    args = parser.parse_args()

    #
    # Load configuration
    #

    # Read in the json file created by the csm_manifest_extractor.py
    csm_extractor_output = None
    with open(args.csm_extractor_output_json, 'r') as f:
        csm_extractor_output = json.load(f)

    if args.csm_release not in csm_extractor_output:
        print(f'Error provided CSM release does not exist in {args.csm_extractor_output_json}')
        exit(1)

    images = csm_extractor_output[args.csm_release]["images"]

    # Global test config
    test_config_global = None
    with open(args.test_config_global, 'r') as f:
        test_config_global = yaml.safe_load(f)

    # Create a lookup table to map image repos to service names
    image_repo_service_lookup = {}
    for name, service in test_config_global["services"].items():
        for image_repo in service["image"]["repo"]["test"].values():
            image_repo_service_lookup[image_repo] = name

    print(json.dumps(image_repo_service_lookup, indent=2))

    # Docker client
    docker_client = docker.from_env()

    # Directories
    allure_dir = pathlib.Path(args.allure_dir)
    tests_output_dir = pathlib.Path(args.tests_output_dir)

    #
    # Identify test images
    #
    hmth_images = []
    for image_repo in images:
        image = f'{image_repo}:{images[image_repo][0]}'
        if image_repo.endswith("hmth-test"):
            # This is a HMTH test
            print(f'Found HMTH test image: {image}')
            hmth_images.append(image)

    #
    # Pull required images
    #
    if not args.skip_pull:
        for image in hmth_images:
            print("Pulling", image)
            docker_client.images.pull(image)

    #
    # Detect tests from test images
    #
    tests = {}

    detected_tests, detected_tavern_configs = detect_test_classes(docker_client, hmth_images, tests_output_dir, wanted_tests = {
        "src/app/smoke.json":                 "smoke",
        "src/app/api/1-non-disruptive/":      "1-non-disruptive",
        "src/app/api/1-hardware-checks/":     "1-hardware-checks",
        "src/app/api/2-disruptive/":          "2-disruptive",
        "src/app/api/3-destructive/":         "3-destructive",
        "src/app/api/4-build-pipeline-only/": "4-build-pipeline-only"
    }, tavern_configs={
        "src/app/tavern_global_config_ct_test.yaml": "default",
        "src/app/tavern_global_config_ct_test_production.yaml": "production",
        "src/app/tavern_global_config_ct_test_emulated_hardware.yaml": "emulated_hardware",
    })
    
    tests = []
    for test_filter in test_config_global["test_order"]: 
        for test_class, images in detected_tests.items():
            # Check to see if there is a matching test class
            if test_filter["test_class"] != test_class:
                continue

            matching_images = []
            for image in images:
                image_repo, image_tag = image.split(":", 2)

                if test_filter["service"] == "all" or test_filter["service"] == image_repo_service_lookup[image_repo]:
                    # Add test if has a matching class and service
                    matching_images.append(image)

            if len(matching_images) != 0:
                tests.append({
                    "test_name": f'{test_class}:{test_filter["service"]}',
                    "test_class": test_class,
                    "images": matching_images
                })

    with open('image_tests.json', 'w') as f:
        json.dump(tests, f, indent=2)

    #
    # Run tests
    #
    if not args.skip_tests:
        run_tests(test_config_global, detected_tavern_configs, tests, allure_dir)

        if args.fix_allure_dir_perms:
            print("Correcting allure report file perms.")
            # This is a hack, but the files created by the docker pytest are own by root in the github action runner
            # for right now just 777 them. 
            result = subprocess.run(["sudo", "chmod", "-R", "777", str(allure_dir)])
            if result.returncode != 0:
                print("Failed to correct allure report files perms. Exit code {}".format(result.returncode))
                print("stderr: {}".format(result.stderr))
                print("stdout: {}".format(result.stdout))
                exit(1)

    #
    # Process test results
    #
    process_allure_reports(allure_dir)


    #
    # Write out test metadata
    #
    test_metadata = {
        "git_sha": csm_extractor_output[args.csm_release]["git_sha"],
        "git_tags": csm_extractor_output[args.csm_release]["git_tags"],
        "images": csm_extractor_output[args.csm_release]["images"],
        "github_action_run_url": None
    }
    if args.github_action_id != "":
        test_metadata["github_action_run_url"] = f'https://github.com/Cray-HPE/hms-nightly-integration/actions/runs/{args.github_action_id}'
    
    test_metadata_file = allure_dir.joinpath("test_metadata.json")
    print(f'Writing out test metadata: {str(test_metadata_file)}')
    with open(test_metadata_file, "w") as f:
        json.dump(test_metadata, f, indent=2)

    #
    # Display summary
    #

    # TODO look at the allure files and output a simple pass/fail count based on image

    print()
    print('View allure report locally')
    print(f'allure serve --host localhost {str(allure_dir)}')