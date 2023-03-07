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
import yaml
import json
import pathlib


if __name__ == "__main__":
    #
    # Parse CLI flags
    #
    parser = argparse.ArgumentParser()
    parser.add_argument("--csm-extractor-output-json", type=str, default="csm-manifest-extractor-output.json", help="Read in the json file created by the csm_manifest_extractor.py")
    parser.add_argument("--csm-release", type=str, default="main", help="CSM release branch to target")
    parser.add_argument("--allure-dir", type=str, default="./allure",  help="Allure output director")
    parser.add_argument("--github-action-id", type=str, default="", help="Github Action run ID")
    parser.add_argument("--step-outcome-standup-simulation-environment", type=str, default="unknown", help="Step outcome for standing up the HMS simulation environment")
    parser.add_argument("--step-outcome-run-tests", type=str, default="unknown", help="Step outcome for running tests. This does not reflect if they were any test failures, only issues running the tests")

    args = parser.parse_args()

    # Create allure_dir if it doesn't exist
    allure_dir = pathlib.Path(args.allure_dir)
    allure_dir.mkdir(parents=True, exist_ok=True)

    # Read in the json file created by the csm_manifest_extractor.py
    csm_extractor_output = None
    with open(args.csm_extractor_output_json, 'r') as f:
        csm_extractor_output = json.load(f)

    if args.csm_release not in csm_extractor_output:
        print(f'Error provided CSM release does not exist in {args.csm_extractor_output_json}')
        exit(1)

    images = csm_extractor_output[args.csm_release]["images"]


    #
    # Write out test metadata
    #
    test_metadata = {
        "git_sha": csm_extractor_output[args.csm_release]["git_sha"],
        "git_tags": csm_extractor_output[args.csm_release]["git_tags"],
        "images": csm_extractor_output[args.csm_release]["images"],
        "github_action_run_url": None,
        "step_outcomes": {
            "standup_simulation_environment": args.step_outcome_standup_simulation_environment,
            "run_tests": args.step_outcome_run_tests,
        }
    }
    if args.github_action_id != "":
        test_metadata["github_action_run_url"] = f'https://github.com/Cray-HPE/hms-nightly-integration/actions/runs/{args.github_action_id}'
    
    test_metadata_file = allure_dir.joinpath("test_metadata.json")
    print(f'Writing out test metadata: {str(test_metadata_file)}')
    with open(test_metadata_file, "w") as f:
        json.dump(test_metadata, f, indent=2)
