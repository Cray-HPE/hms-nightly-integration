#! /usr/bin/env python3

import argparse
import os
import git
import github
import semver
import json
import yaml




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
        print(github_repo)

        repo_application_image_lookup[github_repo] = service["image"]["repo"]["application"]["stable"]
        repo_test_image_lookup[github_repo] = service["image"]["repo"]["test"]["stable"]

        print(repo_application_image_lookup)
        print(repo_test_image_lookup)


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

    
        latest_images[repo_application_image_lookup[github_repo]] = [str(latest_version)]
        print(latest_images)
        print(f'  Latest application image: {repo_application_image_lookup[github_repo]}:{latest_version}')

        latest_images[repo_test_image_lookup[github_repo]] = [str(latest_version)]
        print(f'  Latest test image: {repo_test_image_lookup[github_repo]}:{latest_version}')

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