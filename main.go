package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func getFilesByExt(dirPath, ext string) ([]string, error) {
    entries, err := os.ReadDir(dirPath)
    if err != nil {
        return nil, fmt.Errorf("error reading directory: %w", err)
    }

    var result []string
    for _, entry := range entries {
        if entry.IsDir() {
            continue
        }

        name := entry.Name()

        if strings.HasSuffix(strings.ToLower(name), strings.ToLower(ext)) {
            baseName := strings.TrimSuffix(name, ext)
            result = append(result, baseName)
        }
    }

    return result, nil
}

func openLog(path string) *os.File {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		log.Fatal(err)
	}
	return f
}

func main() {

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

	// Create output directory
	err2 := os.MkdirAll("out", 0755)
	if err2 != nil {
		fmt.Printf("Error %v when attempting to create output directory\n", err)
		return
	}

	variants := []string{"greenfilling", "fcfs", "easy_bf"}

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

						robinLog := openLog("out/robin_" + expFile + ".log")
						defer robinLog.Close()

						// Generate YAML
						generateCmd := exec.Command(
							"robin", "generate", expFile+".yaml",
							"--output-dir=out/log/"+expFile,
							"--batcmd=batsim -p "+platformPath+" -w "+workloadPath+" -e out/log/"+expFile+"/batsim"+" --energy --environmental-footprint-dynamic "+tracePath,
							"--schedcmd=batsched -v "+variant+" --variant_options_filepath "+vOptPath,
						)
						generateCmd.Stdout = robinLog
						generateCmd.Stderr = robinLog
						defer os.Remove(expFile+".yaml")

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
