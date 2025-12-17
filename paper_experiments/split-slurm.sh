#!/bin/bash

# Usage: ./split_and_generate_slurm.sh /path/to/source_dir /path/to/parent_dest_dir name_prefix slurm_partition

SOURCE_DIR="$1"
DEST_PARENT_DIR="$2"
NAME_PREFIX="$3"
SLURM_PART="$4"
MAX_FILES=1000

if [[ -z "$SOURCE_DIR" || -z "$DEST_PARENT_DIR" || -z "$NAME_PREFIX" ]]; then
    echo "Usage: $0 /path/to/source_dir /path/to/parent_dest_dir name_prefix"
    exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "Error: Source directory '$SOURCE_DIR' does not exist."
    exit 2
fi

mkdir -p "$DEST_PARENT_DIR"

SLURM_SCRIPT_DIR="$DEST_PARENT_DIR/slurm-scripts"
LOG_PARENT_DIR="$DEST_PARENT_DIR/slurm-array-logs"

mkdir -p "$SLURM_SCRIPT_DIR"
mkdir -p "$LOG_PARENT_DIR"

file_count=0
dir_count=0

# Make sure files are sorted consistently
FILES=($(ls "$SOURCE_DIR"))

for file in "${FILES[@]}"; do
    # If starting new directory
    if (( file_count % MAX_FILES == 0 )); then
        dir_count=$((dir_count + 1))
        CURRENT_SUBDIR="$DEST_PARENT_DIR/dir_$dir_count"
        mkdir -p "$CURRENT_SUBDIR"
    fi

    # Move the file
    cp "$SOURCE_DIR/$file" "$CURRENT_SUBDIR/"

    file_count=$((file_count + 1))
done

echo "Done splitting $file_count files into $dir_count directories."

# Now, for each split directory, generate a Slurm script and logs subdirs
for d in "$DEST_PARENT_DIR"/dir_*; do
    ABS_PATH=$(realpath "$d")
    DIR_NAME=$(basename "$d")
    JOB_COUNT=$(ls "$d"/*.sh | wc -l)

    # Create output and error subdirectories inside the logs parent
    OUT_DIR="$LOG_PARENT_DIR/${DIR_NAME}/output"
    ERR_DIR="$LOG_PARENT_DIR/${DIR_NAME}/error"
    mkdir -p "$OUT_DIR"
    mkdir -p "$ERR_DIR"

    SLURM_SCRIPT="$SLURM_SCRIPT_DIR/submit_${DIR_NAME}.slurm"

    cat <<EOL > "$SLURM_SCRIPT"
#!/bin/bash
#SBATCH --job-name=${NAME_PREFIX}-${DIR_NAME}
#SBATCH --output=${OUT_DIR}/output_%A_%a.out
#SBATCH --error=${ERR_DIR}/error_%A_%a.err

# Get the list of job files
JOB_FILES=(\$(ls ${ABS_PATH}/*.sh | sort))

# Select the correct job file based on SLURM_ARRAY_TASK_ID
JOB_FILE=\${JOB_FILES[\$((SLURM_ARRAY_TASK_ID-1))]}

sbatch -p $SLURM_PART "\$JOB_FILE"
EOL

    echo "Generated Slurm script: $SLURM_SCRIPT"
done

echo "All done. Slurm scripts are in '$SLURM_SCRIPT_DIR'. Log directories are in '$LOG_PARENT_DIR'."
