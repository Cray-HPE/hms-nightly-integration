#! /usr/bin/env python3

import argparse
import pathlib
import shutil

#
# Parse CLI args
#
parser = argparse.ArgumentParser()
parser.add_argument("reports", type=str, help="Directory containing reports")
parser.add_argument("--max-reports-per-branch", type=int, default=14, help="Max reports per branch")

args = parser.parse_args()

reports_dir = pathlib.Path(args.reports)

# For each branch
# - Prune old reports
# - Generate allure report for each artifact that was generated
#   - Copy history from last run into correct location
# 
# Generate index.html 

#
# Determine if any reports need to be pruned
#
for report_branch_dir in reports_dir.glob("*/"):
    print(report_branch_dir)

    # Find reports for this branch
    found_reports = [] 
    for report_dir in report_branch_dir.glob("*/"):
        found_reports.append(report_dir)

    # Check to see if we now have more than the allowed number of reports
    found_reports.sort()
    for report_dir in found_reports:
        print(" ", report_dir)

    if len(found_reports) > args.max_reports_per_branch:
        prune_count = len(found_reports) - args.max_reports_per_branch
        print(f'  Pruning {prune_count} old report(s). There are {len(found_reports)}, when max allowed is {args.max_reports_per_branch}')


        for report_dir in found_reports[0:prune_count]:
            print(f'  Pruning {report_dir}')
            shutil.rmtree(report_dir)
    else:
        print("No reports to prune")


#
# Generate index.html
#

# TODO