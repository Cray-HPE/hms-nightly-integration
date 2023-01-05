#! /usr/bin/env python3

import argparse
import docker
import json
import shutil
import pathlib
import os
import subprocess
import yaml
import multiprocessing as mp

def mp_extract_tests_from_image(image: str, destination_base: str):
    extract_tests_from_image(docker.from_env(), image, pathlib.Path(destination_base))

def extract_tests_from_image(docker_client: docker.DockerClient, image: str, destination_base: pathlib.Path):
    image_repo, image_tag = image.split(":", 2)

    test_path = destination_base.joinpath(f'{os.path.basename(image_repo)}')
    print(f'Extracting tavern tests from {image} into directory {test_path}')
    test_path.mkdir(exist_ok=True, parents=True)

    # Inspect the container image, without actually running it to determine if this this is a valid image
    container = docker_client.containers.create(image)
    # print(container.id)
    # print(container.name)

    result = subprocess.run(f'docker export {container.name} | tar -C {test_path} --strip-components=1 -xvf - src/', shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print("Failed to extract files from container. Exit code {}".format(result.returncode))
        print("stderr: {}".format(result.stderr))
        print("stdout: {}".format(result.stdout))
        exit(1)

    container.remove()

def extract_tests_from_images(docker_client: docker.DockerClient, images: list[str], destination_base: pathlib.Path):
    if destination_base.exists():
        shutil.rmtree(destination_base)

    print("Starting test extraction")

    use_mp = True
    if use_mp:
        worker_pool = mp.Pool(mp.cpu_count())
        for image in images:            
            worker_pool.apply_async(mp_extract_tests_from_image, args=(image, str(destination_base)), error_callback=lambda x: print(x))
        
        worker_pool.close()
        worker_pool.join() 
    else:
        for image in images:
            extract_tests_from_image(docker_client, image, destination_base)

    print("Test extraction done")

def detect_test_classes(images: list[str], tests_dir: pathlib.Path, wanted_tests: dict):
    results = {}

    for image in images:
        print(f"Detecting tests in {image}")
        image_repo, image_tag = image.split(":", 2)

        for wanted_test in wanted_tests:
            file = tests_dir.joinpath(os.path.basename(image_repo), wanted_test)
            if file.exists():
                print(f"  Found test file: {str(file)}")
                # We have a match!
                test_class = wanted_tests[wanted_test]

                if test_class not in results:
                    results[test_class] = []
                results[test_class].append(image)
            else:
                print(f"  Test file not found: {str(file)}")

    return results

def run_tests(test_global_test_config: dict, tests: dict, allure_report_dir: pathlib.Path):
    # Remove existing reports
    if allure_report_dir.exists():
        shutil.rmtree(allure_report_dir)

    # Build up smoke test lookup map
    # TODO some stream lining could occur if a better structure was used for information reguarding a test
    smoke_host_override = {}
    for service in test_global_test_config["services"]:
        for image_repo in test_global_test_config["services"][service]["image_repos"]:
            smoke_host_override[image_repo] = test_global_test_config["services"][service]["url"]["container"]

    print("Smoke test host overrides")
    print(json.dumps(smoke_host_override, indent=2))

    for test in test_global_test_config["test_order"]:
        test_type = test["test_type"]
        test_class = test["test_class"]

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
            image_repo, image_tag = image.split(":", 2)
            short_name = os.path.basename(image_repo)
            test_path = pathlib.Path("./tests").joinpath(short_name)

            pytest_args = []

            if test_type in ["hmth", "legacy_ct"] and test_class == "smoke":
                pytest_args = ['./smoke', '--smoke-json', str(test_path.joinpath("app", "smoke.json"))]
                
                image_repo, image_tag = image.split(":", 2)
                if image_repo in smoke_host_override:
                    pytest_args = pytest_args + ['--smoke-url', smoke_host_override[image_repo]]
            elif test_type == "legacy_ct" and test_class == "functional":
                # pytest --tavern-global-cfg=tavern_global_config.yaml ./tavern/cray-bss-test --alluredir=./allure/bss
                pytest_args = ['--tavern-global-cfg=tavern_global_config.yaml', str(test_path.joinpath('app'))]
            elif test_type == "hmth":
                pytest_args = ['--tavern-global-cfg=tavern_global_config.yaml', str(test_path.joinpath('app', "api", test_class))]
            else:
                print(f'Unknown test type {test_type}:{test_class}')

            if pytest_args is None:
                print("Skipping unsupported test")
                continue

            cmd = ["docker", "run", "--rm", "-t", 
                "--network", "hms-simulation-environment_simulation",   # Connect to the simulation network 
                "-e", f'PYTHONPATH={str(test_path.joinpath("libs"))}',   # Add additional python lib directories. Some repos have extra python files used by tavern tests
                "-v", f'{str(allure_dir.absolute())}:/allure-results/', # Location to output the allure results
                "hms-nightly-integration-test-runner:local",
                "pytest", "-vvvv", f'--alluredir=/allure-results/{short_name}/{test_class}'
            ] + pytest_args

            print("Command:", ' '.join(cmd))

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                # TODO better message
                print("Tests failed. Exit code {}".format(result.returncode))
                print("stderr: {}".format(result.stderr))
                print("stdout: {}".format(result.stdout))
                continue

            print(result.stdout)

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
        # This will create an heiarchy of:
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
    parser.add_argument("--images-by-csm-release-json", type=str, default="extractor-output-images_by_csm_release.json", help="Read in the json file created by the csm_manifest_extractor.py")
    parser.add_argument("--csm-release", type=str, default="main", help="CSM release branch to target")
    parser.add_argument("--test-config-global", type=str, default="test_config_global.yaml",  help="Global test configuration file")

    parser.add_argument("--allure-dir", type=str, default="./allure",  help="Allure output director")
    parser.add_argument("--tests-output-dir", type=str, default="./tests",  help="Directory to store tests")
    
    parser.add_argument("--skip-pull", type=bool, default=False, action=argparse.BooleanOptionalAction, help="Skipping pulling of images. For local dev only")
    parser.add_argument("--skip-extract", type=bool, default=False, action=argparse.BooleanOptionalAction, help="Skipping extraction of tests. For local dev only")
    parser.add_argument("--skip-tests", type=bool, default=False, action=argparse.BooleanOptionalAction, help="Skipping running of tests. For local dev only")


    args = parser.parse_args()

    #
    # Load configuration
    #

    # Read in the json file created by the csm_manifest_extractor.py
    images_by_csm_release = None
    with open(args.images_by_csm_release_json, 'r') as f:
        images_by_csm_release = json.load(f)

    if args.csm_release not in images_by_csm_release:
        print(f'Error provided CSM release does not exist in {args.images_by_csm_release_json}')
        exit(1)

    images = images_by_csm_release[args.csm_release]

    # Global test config
    test_config_global = None
    with open(args.test_config_global, 'r') as f:
        test_config_global = yaml.safe_load(f)

    # Docker client
    docker_client = docker.from_env()

    # Directories
    allure_dir = pathlib.Path(args.allure_dir)
    tests_output_dir = pathlib.Path(args.tests_output_dir)

    #
    # Identify test images
    #
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

    #
    # Pull required images
    #
    if not args.skip_pull:
        for image in legacy_ct_images + hmth_images:
            print("Pulling", image)
            docker_client.images.pull(image)

    #
    # Extract tests
    #
    if not args.skip_extract:
        extract_tests_from_images(docker_client, legacy_ct_images + hmth_images, tests_output_dir)

    #
    # Detect tests from test images
    #
    tests = {}
    tests["legacy_ct"] = detect_test_classes(legacy_ct_images, tests_output_dir, wanted_tests = {
        "app/smoke_test.py":      "smoke",
        "app/functional_test.py": "functional"
    })

    tests["hmth"] = detect_test_classes(hmth_images, tests_output_dir, wanted_tests = {
        "app/smoke.json":                 "smoke",
        "app/api/1-non-disruptive/":      "1-non-disruptive",
        "app/api/2-disruptive/":          "2-disruptive",
        "app/api/3-destructive/":         "3-destructive",
        "app/api/4-build-pipeline-only/": "4-build-pipeline-only"
    })
    
    with open('image_tests.json', 'w') as f:
        json.dump(tests, f, indent=2)

    #
    # Generate tavern config
    #
    tavern_config = test_config_global["tavern"].copy()
    for service in test_config_global["services"]:
        url = test_config_global["services"][service]["url"]["container"]

        tavern_config["variables"][f'{service.lower()}_base_url'] = url

    with open('tavern_global_config.yaml', 'w') as f:
        yaml.dump(tavern_config, f)

    #
    # Build test image
    #
    print("Building test image")
    result = subprocess.run(["docker", "build", ".", "-t", "hms-nightly-integration-test-runner:local"])
    if result.returncode != 0:
        print("Failed to build files from container. Exit code {}".format(result.returncode))
        print("stderr: {}".format(result.stderr))
        print("stdout: {}".format(result.stdout))
        exit(1)
    print("Test image built")

    #
    # Run tests
    #
    if not args.skip_tests:
        run_tests(test_config_global, tests, allure_dir)

    #
    # Process test results
    #
    process_allure_reports(allure_dir)

    print()
    print('View allure report locally')
    print(f'allure serve --host localhost {str(allure_dir)}')

    #
    # Display summary
    #

    # TODO look at the allure files and output a simple pass/fail count based on image
