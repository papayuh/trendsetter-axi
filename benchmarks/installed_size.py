"""Print RECORD-owned installed bytes separately from source and cache bytes.

Run with each core-only environment's Python; interpreter/venv files are excluded.
"""
import importlib.metadata
import json
from pathlib import Path
import sys

packages = {}
for distribution in importlib.metadata.distributions():
    files = [Path(distribution.locate_file(path)) for path in distribution.files or []]
    packages[distribution.metadata['Name']] = dict(version=distribution.version,
                                                  bytes=sum(path.stat().st_size for path in files if path.is_file()))
print(json.dumps(dict(python=sys.version, packages=packages,
                      total_bytes=sum(package['bytes'] for package in packages.values())), indent=2, sort_keys=True))
