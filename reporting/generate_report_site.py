#! /usr/bin/env python3

import argparse
import pathlib
import shutil
import re
import subprocess
import jinja2
import json

#
# Parse CLI args
#
parser = argparse.ArgumentParser()
parser.add_argument("artifacts", type=str, help="Directory containing artifacts")
parser.add_argument("reports", type=str, help="Directory containing reports")
parser.add_argument("--max-reports-per-branch", type=int, default=14, help="Max reports per branch")

args = parser.parse_args()

artifacts_dir = pathlib.Path(args.artifacts)
reports_dir = pathlib.Path(args.reports)


# For each results artifacts downloaded generate 
#
# For each branch
# - Prune old reports
# - Generate allure report for each artifact that was generated
#   - Copy history from last run into correct location
# 
# Generate index.html 

def find_report_directories(root_dir: pathlib.Path):
    found_dirs = [] 
    for found_dir in root_dir.glob("*/"):
        if not found_dir.is_dir() or found_dir.name == "latest":
            continue
        found_dirs.append(found_dir)

    found_dirs.sort()

    return found_dirs
#
# Detect existing reports
#
existing_reports = {}
print()
print("========================================")
print("Detecting old reports")
print("========================================")
for report_branch_dir in reports_dir.glob("*/"):
    print(f' Processing {report_branch_dir}')

    # Find reports for this branch
    found_reports = find_report_directories(report_branch_dir)

    # Check to see if we now have more than the allowed number of reports
    for report_dir in found_reports:
        print(f'  Found report: {str(report_dir)}')

    existing_reports[report_branch_dir.name] = found_reports

#
# Generate new reports from downloaded artifacts
#
print()
print("========================================")
print("Generating reports")
print("========================================")
for allure_results_dir in artifacts_dir.glob("*/*/"):
    if not allure_results_dir.is_dir():
        continue

    print()
    print(f'Processing {allure_results_dir}')

    # Extract branch and timestamp information
    m = re.search("allure-results-([\d]+)_(.+)", allure_results_dir.parent.name)
    if m is None:
        print(f'  Unable to extract branch information from directory name: {str(allure_results_dir.parent)}')
        continue
    branch_name = m.group(2)
    timestamp = allure_results_dir.name
    print(f'  Branch name: {branch_name}')
    print(f'  Timestamp:   {timestamp}')

    destination_directory = reports_dir.joinpath(branch_name, timestamp)

    # Find previous report for history
    if branch_name in existing_reports and len(existing_reports) > 0:
        previous_report = existing_reports[branch_name][-1]
        print(f'  Previous report: {previous_report}')

        history_dir_source = previous_report.joinpath("history")
        history_dir_destination = allure_results_dir.joinpath("history")

        if history_dir_destination.exists():
            print(f'  Removing existing history destination directory')
            shutil.rmtree(history_dir_destination)
        print(f'  Copying history: {history_dir_source} -> {history_dir_destination}')
        shutil.copytree(history_dir_source, history_dir_destination)

    # Generate the test report
    print(f'  Generating test report into {str(destination_directory)}')
    cmd = ["allure", "generate", "--clean", "-o", str(destination_directory), str(allure_results_dir)]
    print(f'  Running Command: {" ".join(cmd)}')

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("Failed to generate report. Exit code {}".format(result.returncode))
        continue

    # Update latest symlink
    latest_symlink = reports_dir.joinpath(branch_name, "latest")
    print(f"  Updating latest symlink: {latest_symlink} -> {destination_directory}")
    if latest_symlink.is_symlink():
        latest_symlink.unlink()
    latest_symlink.symlink_to(destination_directory.name, target_is_directory=True)

#
# Determine if any reports need to be pruned
#
print()
print("========================================")
print("Pruning old reports")
print("========================================")
for report_branch_dir in reports_dir.glob("*/"):
    print(f' Processing {report_branch_dir}')

    # Find reports for this branch
    found_reports = find_report_directories(report_branch_dir)

    # Check to see if we now have more than the allowed number of reports
    for report_dir in found_reports:
        print(f'  Found report: {str(report_dir)}')

    if len(found_reports) > args.max_reports_per_branch:
        prune_count = len(found_reports) - args.max_reports_per_branch
        print(f'  Pruning {prune_count} old report(s). There are {len(found_reports)}, when max allowed is {args.max_reports_per_branch}')


        for report_dir in found_reports[0:prune_count]:
            print(f'  Pruning {report_dir}')
            shutil.rmtree(report_dir)
    else:
        print(f'  No reports to prune for branch {report_branch_dir}')

#
# Generate index.html for each branch
#

print()
print("========================================")
print("Generating index.yaml for each release branch")
print("========================================")
template_data = {"releases": []}
for report_branch_dir in reports_dir.glob("*/"):
    if not report_branch_dir.is_dir():
        continue
    print(f' Processing {report_branch_dir}')

    # Find reports for this branch
    found_reports = find_report_directories(report_branch_dir)
    found_reports.reverse()

    release_branch_data = {}
    release_branch_data["release"] = report_branch_dir.name.removesuffix("/")
    release_branch_data["reports"] = []
    for report_dir in found_reports:
        print(f'  Found report: {str(report_dir)}')

        # Read in latest report summary
        report_data = {}
        report_data["date"] = report_dir.name
        with open(report_branch_dir.joinpath("latest", "widgets", "summary.json")) as f:
            summary = json.load(f)

            report_data["total_tests"] = summary["statistic"]["total"]
            report_data["passed_tests"] = summary["statistic"]["passed"]
            report_data["failed_tests"] = report_data["total_tests"] -  report_data["passed_tests"]

        release_branch_data["reports"].append(report_data)

    template_data["releases"].append(release_branch_data)

template_data["releases"].sort(key=lambda x: x["release"])
print(json.dumps(template_data, indent=2))

# Generate report HTML
environment = jinja2.Environment(loader=jinja2.FileSystemLoader("./reporting/"))
index_html_template = environment.get_template("index.html.j2")
index_html_content = index_html_template.render(template_data)

# Write out the generated file
index_html_path = reports_dir.joinpath("index.html")
print(f'  Writing index page: {str(index_html_path)}')
with open(index_html_path, 'w') as f:
    f.write(index_html_content)
