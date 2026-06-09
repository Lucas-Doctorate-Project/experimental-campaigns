# Bash Implementation

This folder contains the bash-based experimental campaign runner.

## Files

- `runner.sh`: starts Batsim and Batsched for each experiment in a TOML campaign file.
- `parse_toml.py`: converts the TOML campaign into tab-separated rows that the shell script consumes.

## Usage

Run the script from the `experimental-campaigns` directory, so relative paths in the campaign file resolve as expected.

```sh
./bash/runner.sh example/experiments.toml
```

The script resolves `parse_toml.py` relative to its own location. The parser currently uses Python's `tomllib` module, so it requires Python 3.11 or newer.

## Output

Artifacts are written to the `out/` directory in your current working directory.
