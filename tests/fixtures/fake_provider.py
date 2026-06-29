#!/usr/bin/env python3
"""Offline CLI provider fixture controlled through stdin."""
import json
import os
import sys
import time

prompt = sys.stdin.read()
if prompt.startswith("TIMEOUT"):
    time.sleep(10)
elif prompt.startswith("FAIL"):
    print("fake provider failure", file=sys.stderr)
    raise SystemExit(7)
elif prompt.startswith("ENV"):
    print(json.dumps(dict(os.environ), sort_keys=True))
elif prompt.startswith("LARGE"):
    print("x" * 4096)
elif "Original request:" in prompt:
    print('{"mode":"code","intent":"modify_code","confidence":0.75}')
elif prompt.startswith("MALFORMED"):
    print("not json")
else:
    print(prompt)
