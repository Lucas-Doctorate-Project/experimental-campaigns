package main

import (
	"log"
	"os"
	"os/exec"
)

func openLog(path string) *os.File {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		log.Fatal(err)
	}
	return f
}

func main() {
	batschedLog := openLog("out/batsched.log")
	defer batschedLog.Close()

	batsimLog := openLog("out/batsim.log")
	defer batsimLog.Close()

	batschedCmd := exec.Command("batsched", "-v", "greenfilling", "--variant_options", `{"intensity_trace": "example/trace.csv", "intensity_zone": "AS0", "smoothing_factor": 0.3, "ema_threshold": 1.0, "backfilling_combinator": "and", "greenfilling_debug": true}`)
	batschedCmd.Stdout = batschedLog
	batschedCmd.Stderr = batschedLog

	batsimCmd := exec.Command("batsim", "-p", "example/platform.xml", "-w", "example/workload.json", "-e", "out/logs", "--energy", "--environmental-footprint-dynamic", "example/trace.csv")
	batsimCmd.Stdout = batsimLog
	batsimCmd.Stderr = batsimLog

	if err := batschedCmd.Start(); err != nil {
		log.Fatal(err)
	}
	if err := batsimCmd.Start(); err != nil {
		log.Fatal(err)
	}

	batschedCmd.Wait()
	batsimCmd.Wait()
}
