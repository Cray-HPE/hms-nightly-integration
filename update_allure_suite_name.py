#! /usr/bin/env python3

import argparse
import pathlib
import json


def update_allure_suite_name(allure_report_dir):
    for test_result_path in pathlib.Path(allure_report_dir).glob("**/*.json"):
        test_source = test_result_path.parent.parent.name
        test_class = test_result_path.parent.name
        print(test_source, test_class, test_result_path.name) 
        
        # Read in test result file
        test_result = None
        with open(test_result_path, 'r') as f:
            test_result = json.load(f)

        # Fix the suite name
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

def generate_allure_report(allure_report_dir):
    report_dirs = []
    for test_result_path in pathlib.Path(allure_report_dir).glob("*/*/"):
        if test_result_path.is_dir():
            report_dirs.append(str(test_result_path))

    cmd = ["allure", "generate", "-o", "allure_report"] + report_dirs
    print(' '.join(cmd))

    cmd = ["allure", "serve", "--host", "localhost"] + report_dirs
    print(' '.join(cmd))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("allure_report_dir", type=str, help="Directory containing directories of allure reports for each HMS service")

    args = parser.parse_args()

    update_allure_suite_name(args.allure_report_dir)
    generate_allure_report(args.allure_report_dir)






