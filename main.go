// Package main runs a campaign of Batsim and Batsched simulations defined
// in a TOML file. Each experiment runs batsim and batsched as co-running
// processes and writes artifacts into its own directory.
package main

import (
	"flag"
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/BurntSushi/toml"
)

// runOptions carries the execution policy shared by all experiments.
// socket is the address batsim must bind. simulationTimeout caps the
// runtime of one experiment. failureTimeout and successTimeout are the
// grace periods granted to the surviving process after the other exits
// with a non-zero or zero status.
type runOptions struct {
	socket            string
	simulationTimeout time.Duration
	failureTimeout    time.Duration
	successTimeout    time.Duration
}

// Experiment describes one run decoded from the campaign TOML.
// Name is the output directory. Workload, Platform and EnvironmentalTrace
// are input paths resolved relative to the working directory. VariantName
// selects the Batsched variant. VariantOptions is the JSON file passed
// as --variant_options_filepath.
type Experiment struct {
	Name               string `toml:"name"`
	Workload           string `toml:"workload"`
	Platform           string `toml:"platform"`
	EnvironmentalTrace string `toml:"environmental_trace"`
	VariantName        string `toml:"variant_name"`
	VariantOptions     string `toml:"variant_options"`
}

// Campaign is the top-level TOML structure, an ordered list of experiments
// executed sequentially.
type Campaign struct {
	Experiments []Experiment `toml:"experiment"`
}

// openFile opens path for appending, creating it with mode 0644 if
// absent. It calls log.Fatal on failure. The caller closes the file.
func openFile(path string) *os.File {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)

	if err != nil {
		log.Fatal(err)
	}

	return f
}

// socketInUse reports whether the TCP endpoint in addr is currently
// bound. A "tcp://" prefix in addr is stripped. The check attempts a
// bind and immediately closes on success.
func socketInUse(addr string) bool {
	hostPort := strings.TrimPrefix(addr, "tcp://")
	ln, err := net.Listen("tcp", hostPort)
	if err != nil {
		return true
	}
	ln.Close()
	return false
}

// killGroup terminates the process group led by cmd and any children
// it spawned. It is a no-op when cmd is nil or unstarted. It sends
// SIGTERM, waits 500 ms, then sends SIGKILL. cmd must have been started
// with SysProcAttr.Setpgid set.
func killGroup(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	pgid := cmd.Process.Pid
	_ = syscall.Kill(-pgid, syscall.SIGTERM)
	time.Sleep(500 * time.Millisecond)
	_ = syscall.Kill(-pgid, syscall.SIGKILL)
}

// waitWithTimeouts waits for both processes to exit under the policy in
// opts. A simulation timer runs from entry. When the first process
// exits, a second timer arms for successTimeout or failureTimeout
// depending on its exit status. Any timer firing kills both groups and
// drains the pending Wait calls. The function returns nil only when
// both processes exit cleanly.
func waitWithTimeouts(batsched, batsim *exec.Cmd, opts runOptions) error {
	batschedDone := make(chan error, 1)
	batsimDone := make(chan error, 1)
	go func() { batschedDone <- batsched.Wait() }()
	go func() { batsimDone <- batsim.Wait() }()

	simTimer := time.NewTimer(opts.simulationTimeout)
	defer simTimer.Stop()

	var batschedErr, batsimErr error
	var batschedDoneFlag, batsimDoneFlag bool
	var crossTimer *time.Timer
	var crossTimerC <-chan time.Time

	for !batschedDoneFlag || !batsimDoneFlag {
		if batschedDoneFlag != batsimDoneFlag && crossTimer == nil {
			firstErr := batschedErr
			if batsimDoneFlag {
				firstErr = batsimErr
			}
			d := opts.successTimeout
			if firstErr != nil {
				d = opts.failureTimeout
			}
			crossTimer = time.NewTimer(d)
			crossTimerC = crossTimer.C
		}

		select {
		case err := <-batschedDone:
			batschedErr = err
			batschedDoneFlag = true
		case err := <-batsimDone:
			batsimErr = err
			batsimDoneFlag = true
		case <-simTimer.C:
			killGroup(batsched)
			killGroup(batsim)
			if !batschedDoneFlag {
				<-batschedDone
			}
			if !batsimDoneFlag {
				<-batsimDone
			}
			if crossTimer != nil {
				crossTimer.Stop()
			}
			return fmt.Errorf("simulation timeout exceeded (%s)", opts.simulationTimeout)
		case <-crossTimerC:
			killGroup(batsched)
			killGroup(batsim)
			if !batschedDoneFlag {
				<-batschedDone
			}
			if !batsimDoneFlag {
				<-batsimDone
			}
			return fmt.Errorf("other process did not finish within grace period")
		}
	}

	if crossTimer != nil {
		crossTimer.Stop()
	}
	if batschedErr != nil || batsimErr != nil {
		return fmt.Errorf("batsched=%v batsim=%v", batschedErr, batsimErr)
	}
	return nil
}

// runExperiment executes one experiment under opts. It creates
// exp.Name, checks opts.socket is free, opens the four log files, then
// starts batsched and batsim in their own process groups and delegates
// to waitWithTimeouts. Returns nil only when both processes exit
// cleanly.
func runExperiment(exp Experiment, opts runOptions) error {
	outputDir := exp.Name
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return fmt.Errorf("creating output dir: %w", err)
	}

	if socketInUse(opts.socket) {
		return fmt.Errorf("socket %s already in use (another batsim?)", opts.socket)
	}

	batschedLog := openFile(filepath.Join(outputDir, "batsched.log"))
	defer batschedLog.Close()
	batschedErr := openFile(filepath.Join(outputDir, "batsched.err"))
	defer batschedErr.Close()
	batsimLog := openFile(filepath.Join(outputDir, "batsim.log"))
	defer batsimLog.Close()
	batsimErr := openFile(filepath.Join(outputDir, "batsim.err"))
	defer batsimErr.Close()

	batschedCmd := exec.Command("batsched",
		"-v", exp.VariantName,
		"--variant_options_filepath", exp.VariantOptions,
	)
	batschedCmd.Stdout = batschedLog
	batschedCmd.Stderr = batschedErr
	batschedCmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	batsimCmd := exec.Command("batsim",
		"-p", exp.Platform,
		"-w", exp.Workload,
		"-e", filepath.Join(outputDir, "out"),
		"--energy",
		"--environmental-footprint-dynamic", exp.EnvironmentalTrace,
	)
	batsimCmd.Stdout = batsimLog
	batsimCmd.Stderr = batsimErr
	batsimCmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	if err := batschedCmd.Start(); err != nil {
		return fmt.Errorf("starting batsched: %w", err)
	}
	if err := batsimCmd.Start(); err != nil {
		killGroup(batschedCmd)
		_ = batschedCmd.Wait()
		return fmt.Errorf("starting batsim: %w", err)
	}

	return waitWithTimeouts(batschedCmd, batsimCmd, opts)
}

// main parses flags, decodes the campaign TOML, and runs each
// experiment in sequence. A failed experiment does not abort the
// campaign. Exits 0 only when every experiment succeeds, 1 otherwise.
func main() {
	campaignPath := flag.String("campaign", "example/experiments.toml", "Path to the campaign TOML file")
	socket := flag.String("socket", "tcp://localhost:28000", "Batsim socket address")
	simulationTimeout := flag.Duration("simulation-timeout", time.Hour, "Maximum runtime for a single experiment")
	failureTimeout := flag.Duration("failure-timeout", 30*time.Second, "Grace period for the surviving process after the other fails")
	successTimeout := flag.Duration("success-timeout", 30*time.Second, "Grace period for the surviving process after the other succeeds")
	flag.Parse()

	opts := runOptions{
		socket:            *socket,
		simulationTimeout: *simulationTimeout,
		failureTimeout:    *failureTimeout,
		successTimeout:    *successTimeout,
	}

	var campaign Campaign
	if _, err := toml.DecodeFile(*campaignPath, &campaign); err != nil {
		log.Fatal(err)
	}

	failed := 0
	for _, exp := range campaign.Experiments {
		fmt.Printf("Running experiment: %s\n", exp.Name)
		if err := runExperiment(exp, opts); err != nil {
			fmt.Fprintf(os.Stderr, "experiment %q failed: %v\n", exp.Name, err)
			failed++
		}
	}

	if failed > 0 {
		os.Exit(1)
	}
}
