package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// ... (keep your getFilesByExt and openLog functions exactly as they are) ...

func main() {
	robinLog := openLog("out/robin.log")
	defer robinLog.Close()

	// Declare variables properly
	platformsDir := "example/"
	platforms, err := getFilesByExt(platformsDir, ".xml")
	if err != nil {
		fmt.Println("error when parsing platform files:", err)
		return
	}

	workloadsDir := "example/"
	workloads, err := getFilesByExt(workloadsDir, ".json")
	if err != nil {
		fmt.Println("error when parsing workload files:", err)
		return
	}

	tracesDir := "example/"
	traces, err := getFilesByExt(tracesDir, ".csv")
	if err != nil {
		fmt.Println("error when parsing trace files:", err)
		return
	}

	vOptDir := "variants/"
	vOpts, err := getFilesByExt(vOptDir, ".json")
	if err != nil {
		fmt.Println("error when parsing variant options files:", err)
		return
	}

	variants := []string{"greenfilling", "fcfs", "saf"}

	for _, variant := range variants {
		for _, vOptions := range vOpts {
			for _, platform := range platforms {
				for _, workload := range workloads {
					for _, traceFile := range traces {
						// Construct experiment name
						expFile := variant + "_" + platform + "_" + workload + "_" + traceFile + "_" + vOptions
						
						// Re-add extensions for the actual file paths
						platformPath := filepath.Join(platformsDir, platform+".xml")
						workloadPath := filepath.Join(workloadsDir, workload+".json")
						tracePath := filepath.Join(tracesDir, traceFile+".csv")
						vOptPath := filepath.Join(vOptDir, vOptions+".json")

						// Generate YAML
						generateCmd := exec.Command(
							"robin", "generate", expFile+".yaml",
							"--output-dir=out/log/"+expFile,
							"--batcmd=batsim -p "+platformPath+" -w "+workloadPath+" -e out/log/batsim_"+expFile+" --energy --environmental-footprint-dynamic "+tracePath,
							"--schedcmd=batsched -v "+variant+" --variant_options_file "+vOptPath,
						)
						generateCmd.Stdout = robinLog
						generateCmd.Stderr = robinLog

						if err := generateCmd.Run(); err != nil {
							log.Printf("Error generating experiment %s: %v", expFile, err)
							continue
						}

						// Run the experiment
						runCmd := exec.Command("robin", "./"+expFile+".yaml")
						runCmd.Stdout = robinLog
						runCmd.Stderr = robinLog

						if err := runCmd.Run(); err != nil {
							log.Printf("Error running experiment %s: %v", expFile, err)
						}
					}
				}
			}
		}
	}
}
