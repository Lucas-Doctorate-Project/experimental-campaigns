# Experimental Campaigns

Runner for campaigns of Batsim simulations driven by the Batsched scheduler. Each experiment launches Batsim and Batsched as a pair of co-running processes wired over a ZMQ socket. The runner captures their logs, enforces timeouts, and writes artifacts into a per-experiment directory.

## Set up the dev shell

The flake provides `go`, `batsim`, and `batsched` on the `PATH`.

```sh
nix develop
```

All commands below assume you are inside this shell.

## Declare a campaign

A campaign is a TOML file with one or more `[[experiment]]` tables.

```toml
[[experiment]]

name = "example-exp"
workload = "example/workload.json"
platform = "example/platform.xml"
environmental_trace = "example/environmental.csv"
variant_name = "greenfilling"
variant_options = "example/options.json"
```

Fields.

- `name`: output directory name for the experiment artifacts under `out/`. Created if absent.
- `workload`: path to the Batsim workload JSON.
- `platform`: path to the SimGrid platform XML.
- `environmental_trace`: path passed to Batsim as `--environmental-footprint-dynamic`.
- `variant_name`: Batsched variant, passed as `-v`.
- `variant_options`: path passed to Batsched as `--variant_options_filepath`.

Paths are resolved by the OS, so use absolute paths or paths relative to the directory you run the binary from. Append more `[[experiment]]` tables to add experiments.

Experiment names must be unique within one campaign. The runner uses `name` for the output directory under `out/`.

## Declare variant options

The file referenced by `variant_options` is JSON handed to Batsched untouched. For the `greenfilling` variant.

```json
{
    "intensity_trace": "example/environmental.csv",
    "intensity_zone": "AS0",
    "smoothing_factor": 0.3,
    "ema_threshold": 1.0,
    "backfilling_combinator": "and",
    "greenfilling_debug": true
}
```

See the Batsched documentation for the keys accepted by each variant.

## Run a campaign

```sh
go run . --campaign example/experiments.toml
```

Flags.

| Flag | Default | Purpose |
| --- | --- | --- |
| `--campaign` | `experiments.toml` | Path to the campaign TOML file. |
| `--simulation-timeout` | `1h` | Max wall-clock time per experiment. |
| `--failure-timeout` | `30s` | Grace period after the other process fails. |
| `--success-timeout` | `30s` | Grace period after the other process exits cleanly. |

The runner launches experiments in declaration order, with up to `runtime.NumCPU()` experiments running at once. Each experiment gets its own temporary IPC socket endpoint. The runner exits `0` only when every experiment succeeds. A failure does not interrupt the remaining experiments, the program exits `1` at the end.

## Inspect the output

For an experiment named `example-exp`.

- `out/example-exp/batsched.log`, `out/example-exp/batsched.err`: Batsched stdout and stderr.
- `out/example-exp/batsim.log`, `out/example-exp/batsim.err`: Batsim stdout and stderr.
- `out/example-exp/out_*.csv`: Batsim exports. Main ones are `out_jobs.csv` (per-job metrics) and `out_schedule.csv` (run aggregates).

Log files are opened in append mode. Delete the directory between runs for a clean slate.
