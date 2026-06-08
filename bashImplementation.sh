#!/bin/bash

# === CONFIGURATION PARAMETERS ===
NPROC=$(($(nproc) / 2))
if [ "${NPROC}" -le 0 ]; then
    NPROC=1
fi

OUTPUT_DIR="out"

if [ ${#} -le 0 ]; then
	echo "ERROR: missing argument: .toml experiments file to be used."
	echo "Syntax: ${0} [file]"
	exit 1
fi

TOML_FILE=${1}

mkdir -p "${OUTPUT_DIR}"

# === MAIN LOOP ===
echo "Parsing experiments data from ${TOML_FILE}..."
ITERATOR=0

# Reads the output of parse_toml.py line by line
while IFS=$'\t' read -r NAME VARIANT PLATFORM WORKLOAD TRACE VOPTS; do
    
    # Resolves absolute paths and skips iteration if any file is not found
    FULL_PLATFORM=$(realpath "${PLATFORM}" 2>/dev/null || echo "${PLATFORM}")
    FULL_WORKLOAD=$(realpath "${WORKLOAD}" 2>/dev/null || echo "${WORKLOAD}")
    FULL_TRACE=$(realpath "${TRACE}" 2>/dev/null || echo "${TRACE}")
    FULL_VOPTS=$(realpath "${VOPTS}" 2>/dev/null || echo "${VOPTS}")
    
    for FILENAME in ${FULL_PLATFORM} ${FULL_WORKLOAD} ${FULL_TRACE} ${FULL_VOPTS}; do
        if [ ! -f "${FILENAME}" ]; then
            echo "[${NAME}] WARNING: file ${FILENAME} not found. Skipping."
            continue
        fi
    done
    # End of file name validation
    
    # Checks if the number of child jobs does not surpass the number of threads we want to be used 
    while [ $(jobs -r | wc -l) -ge "${NPROC}" ]; do
        sleep 1
    done
    
    ITERATOR=$((ITERATOR + 1))
    
    echo "[${NAME}] Variant: ${VARIANT} | Platform: ${PLATFORM} | Workload: ${WORKLOAD} | Trace: ${TRACE} | Vopts: ${VOPTS}"
    
    (
        batsim -p "${FULL_PLATFORM}" \
               -w "${FULL_WORKLOAD}" \
               -e "${OUTPUT_DIR}/batsim_${NAME}" \
               --socket-endpoint "ipc://socket_${NAME}" \
               --energy \
               --environmental-footprint-dynamic "${FULL_TRACE}" &> /dev/null &&
	       echo "[${ITERATOR}] Batsim finished successfuly." ||
	       echo "[${ITERATOR}] ERROR: BATSIM finished forcefully." && exit &

        batsched -v "${VARIANT}" \
                 --variant_options_filepath="${FULL_VOPTS}" \
                 --socket-endpoint="ipc://socket_${NAME}" &> "${OUTPUT_DIR}/batsched_${NAME}" &&
	         echo "[${ITERATOR}] Batsched finished successfuly." ||
	         echo "[${ITERATOR}] ERROR: BATSCHED finished forcefully." &
	
        wait
    ) &
    
done < <(eval "python3 parse_toml.py ${TOML_FILE}")


wait
rm socket_*
echo "All jobs finished"

exit 0
