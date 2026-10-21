#!/usr/bin/env python3
"""Tiny bounded paired clock sample. Both clocks observed in the same process."""
import json
import time
from pathlib import Path
import sys
out=Path(sys.argv[1])
a=time.time_ns()
m=time.monotonic_ns()
b=time.time_ns()
if a>b or b-a>=50_000_000:
    raise SystemExit("Unstable paired host clocks")
out.write_text(json.dumps({
    "wall_before_ns":a,"monotonic_ns":m,"wall_after_ns":b,
},sort_keys=True)+"\n")
