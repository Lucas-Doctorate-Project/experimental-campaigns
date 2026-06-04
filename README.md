# Greenfilling Experiments

Runner for experimenting with the `greenfilling` Batsched scheduling variant on top of Batsim. It launches Batsim and Batsched as sibling processes, wires them together over the default socket, and captures their logs.

The included `example/` directory contains an example scenario:

- `platform.xml`: a 1600-resource SimGrid platform.
- `workload.json`: the job stream Batsim replays.
- `trace.csv`: a time series of carbon and water intensity values for zone `AS0`, fed to both Batsim (as a dynamic environmental footprint) and Batsched (as the intensity trace driving greenfilling decisions).

The `variants/` directory is where all json configuration files for `batsched` is stored. Batsched uses them with the `--variant_options_filepath` parameter. It contains `config1.json` by default.

## Running

The flake provides a dev shell with `go`, `batsim`, and `batsched` on the `PATH`. From the repository root:

```sh
nix develop
mkdir -p out
go run .
```

`main.go` invokes:

- `batsched -v greenfilling` with `intensity_trace=example/trace.csv`, `intensity_zone=AS0`, `smoothing_factor=0.3`, `ema_threshold=1.0`, `backfilling_combinator=and`, and `greenfilling_debug=true`.
- `batsim -p example/platform.xml -w example/workload.json -e out/logs --energy --environmental-footprint-dynamic example/trace.csv`.

## Output

Everything lands under `out/`:

- `out/batsched.log`: stdout and stderr from Batsched, including the greenfilling debug trace.
- `out/batsim.log`: stdout and stderr from Batsim.
- `out/logs_*.csv` and related files: Batsim's per-job, per-machine, and energy/footprint exports, prefixed with `logs` because of the `-e out/logs` flag. The main ones are `logs_jobs.csv` (per-job makespan, waiting time, consumed energy) and `logs_schedule.csv` (aggregate metrics for the run).
