if [ $# -gt 0 ]; then
    slurmpartname=$1
else
    echo "Usage: $0 <slurmpartname>"
    exit 1
fi

python3.12 -m venv $(pwd)/venv
source $(pwd)/venv/bin/activate
pip install setuptools
pip install unified-planning
pip install --no-cache up-symk
pip install lark
pip install up-fast-downward
pip install .
mkdir -p $(pwd)/sandbox-benchmark/classical-domains
git clone --recursive https://github.com/AI-Planning/classical-domains.git $(pwd)/sandbox-benchmark/classical-domains
python $(pwd)/paper_experiments/generate-benchmark-slurm-tasks.py --sandbox-dir $(pwd)/sandbox-benchmark --planning-tasks-dir $(pwd)/sandbox-benchmark/classical-domains/classical --resources-dir $(pwd)/paper_experiments/data/classical-domains-ru-info
sh $(pwd)/paper_experiments/split-slurm.sh $(pwd)/sandbox-benchmark/slurm-dumps $(pwd)/sandbox-benchmark/splitted-slurm-dumps asp-run $slurmpartname
pip uninstall pypmt
pip install git+https://github.com/pyPMT/pyPMT.git@d44efb71746b3a91e7fb1926b4405bd14f9df33b
deactivate
