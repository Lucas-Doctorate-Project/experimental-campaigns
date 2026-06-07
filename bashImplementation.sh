#!/bin/bash

# === CONFIGURAÇÃO GERAL ===
NPROC=$(($(nproc) / 2))
if [ "${NPROC}" -le 0 ]; then
    NPROC=1
fi

PLATFORMS_DIR="platforms"
WORKLOADS_DIR="workloads"
TRACES_DIR="traces"
OUTPUT_DIR="out"
VOPTS_DIR="vopts"
TOML_FILE="experiments.toml"

mkdir -p "${OUTPUT_DIR}"

# === FUNÇÃO PARA LER O TOML ===
# Usa python3 com tomllib (Python 3.11+) ou 'toml' package
read_toml_experiments() {
    python3 << PYTHON_SCRIPT
import sys
import json
try:
    import tomllib
except ImportError:
    try:
        import toml as tomllib
    except ImportError:
        print("Erro: python-3.11+ necessário ou pacote 'pip install toml'", file=sys.stderr)
        sys.exit(1)

config_file = "${TOML_FILE}"

try:
    with open(config_file, "rb") as f:
        data = tomllib.load(f)
except FileNotFoundError:
    print(f"Erro: Arquivo {config_file} não encontrado.", file=sys.stderr)
    sys.exit(1)

for exp in data.get("experiment", []):
    # Formato: ID<TAB>VARIANT<TAB>PLATFORM<TAB>WORKLOAD<TAB>TRACE<TAB>VOPTS
    
    # Suporta string única ou lista
    name = exp.get("name", "")
    platform = exp.get("platform", "")
    workload = exp.get("workload", "")
    trace = exp.get("environmental_trace", "")
    variant = exp.get("variant_name", "")
    vopts = exp.get("variant_options", "")
    
    # Garante arrays se necessário
    if isinstance(name, list): name = ",".join(name)
    if isinstance(platform, list): platform = ",".join(platform)
    if isinstance(workload, list): workload = ",".join(workload)
    if isinstance(trace, list): trace = ",".join(trace)
    if isinstance(variant, list): variant = ",".join(variant)
    if isinstance(vopts, list): vopts = ",".join(vopts)
    
    # Imprime separando por tab (\t)
    print(f"{name}\t{variant}\t{platform}\t{workload}\t{trace}\t{vopts}")
PYTHON_SCRIPT
}

# === LOOP PRINCIPAL ===
echo "Parsing experiments data from ${TOML_FILE}..."
ITERATOR=0

# Lê o output do Python linha por linha
while IFS=$'\t' read -r NAME VARIANT PLATFORM WORKLOAD TRACE VOPTS; do
    # Pulsa linhas vazias
    [ -z "${NAME}" ] && continue
    
    # Resolve paths absolutos (CRÍTICO para evitar erros de arquivo não encontrado)
    # Remove espaços extras e converte para absoluto
    FULL_PLATFORM=$(realpath "${PLATFORM}" 2>/dev/null || echo "${PLATFORM}")
    FULL_WORKLOAD=$(realpath "${WORKLOAD}" 2>/dev/null || echo "${WORKLOAD}")
    FULL_TRACE=$(realpath "${TRACE}" 2>/dev/null || echo "${TRACE}")
    FULL_VOPTS=$(realpath "${VOPTS}" 2>/dev/null || echo "${VOPTS}")
    
    # Validação básica
    for FILENAME in ${FULL_PLATFORM} ${FULL_WORKLOAD} ${FULL_TRACE} ${FULL_VOPTS}; do
        if [ ! -f "${FILENAME}" ]; then
            echo "[${NAME}] WARNING: file ${FILENAME} not found. Skipping."
            continue
        fi
    done
    
    # Contagem de jobs ativos (Lógica de Limite)
    while [ $(jobs -r | wc -l) -ge "${NPROC}" ]; do
        sleep 1
    done
    
    ITERATOR=$((ITERATOR + 1))
    
    echo "[${NAME}] Variant: ${VARIANT} | Platform: ${PLATFORM} | Workload: ${WORKLOAD} | Trace: ${TRACE} | Vopts: ${VOPTS}"
    
    # Execução (Subshell agrupa commands para controle de job)
    (
        batsim -p "${FULL_PLATFORM}" \
               -w "${FULL_WORKLOAD}" \
               -e "${OUTPUT_DIR}/batsim_${NAME}" \
               --socket-endpoint "ipc://socket_${NAME}" \
               --energy \
               --environmental-footprint-dynamic "${FULL_TRACE}" &> /dev/null &&
	       echo "[${ITERATOR}] Batsim finished successfuly." ||
	       echo "[${ITERATOR}] ERROR: BATSIM finished forcefully." && exit &

	#BATSCHED_PID=$!

        # 3. AGUARDA AMBOS TERMINAREM DENTRO DO SUBSHELL
        #wait $BATSIM_PID
        #EXIT_SIM=$?
        
        # Espera batsim terminar antes de iniciar batsched se compartilharem socket?
        # No seu script original eram paralelos. Aqui mantemos paralelo mas no mesmo grupo.
        batsched -v "${VARIANT}" \
                 --variant_options_filepath="${FULL_VOPTS}" \
                 --socket-endpoint="ipc://socket_${NAME}" &> "${OUTPUT_DIR}/batsched_${NAME}" &&
	         echo "[${ITERATOR}] Batsched finished successfuly." ||
	         echo "[${ITERATOR}] ERROR: BATSCHED finished forcefully." &
	
        wait
    ) &
    
done < <(read_toml_experiments)


#while [ $(jobs -r | wc -l) -gt 0 ]; do
#	sleep 2
#done
wait
rm socket_*
echo "All jobs finished"
