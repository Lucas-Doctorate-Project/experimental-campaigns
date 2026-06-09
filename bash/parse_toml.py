import sys
import json
import tomllib

config_file = sys.argv[1] 

try:
    with open(config_file, "rb") as f:
        data = tomllib.load(f)
except FileNotFoundError:
    print(f"ERROR: Experiments file {config_file} not found. Exiting", file=sys.stderr)
    sys.exit(1)

for exp in data.get("experiment", []):
    
    name = exp.get("name", "")
    platform = exp.get("platform", "")
    workload = exp.get("workload", "")
    trace = exp.get("environmental_trace", "")
    variant = exp.get("variant_name", "")
    vopts = exp.get("variant_options", "")
    
    # Prints all variables, separated by tabspaces (\t)
    print(f"{name}\t{variant}\t{platform}\t{workload}\t{trace}\t{vopts}")
