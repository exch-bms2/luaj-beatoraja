#!/usr/bin/env python3
"""Fail on test failures absent from the explicitly recorded upstream baseline."""
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

baseline = json.loads(pathlib.Path(sys.argv[1]).read_text())
observed = set()
tests = 0
for path in pathlib.Path(sys.argv[2]).glob("TEST-*.xml"):
    for case in ET.parse(path).getroot().findall("testcase"):
        tests += 1
        if case.find("failure") is not None or case.find("error") is not None:
            observed.add(case.attrib["classname"] + "." + case.attrib["name"])
new = observed - baseline["failures"].keys()
if tests < baseline["minimum_test_cases"]:
    sys.exit("Incomplete test reports: " + str(tests))
print(f"Test cases: {tests}; known failures: {len(observed)}; new failures: {len(new)}")
for name in sorted(new):
    print(name)
sys.exit(bool(new))
