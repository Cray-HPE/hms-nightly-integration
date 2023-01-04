#! /usr/bin/env python3

import json
import requests
from urllib.parse import urljoin

def test_smoke(smoke_test_data):

    req = requests.request(url=smoke_test_data["url"], method=str(smoke_test_data["method"]).upper(), data=smoke_test_data["body"],
                                   headers=smoke_test_data["headers"])

    assert req.status_code == smoke_test_data["expected_status_code"], "unexpected status code."
