if [ $# -gt 0 ]; then
    slurmpartname=$1
else
    echo "Usage: $0 <slurmpartname>"
    exit 1
fi

python3.13 -m venv $(pwd)/venv
source $(pwd)/venv/bin/activate
pip install setuptools
pip install unified-planning
pip install --no-cache up-symk
pip install git+https://github.com/MFaisalZaki/forbiditerative.git
pip install lark
pip install up-fast-downward
pip install matplotlib 
pip install seaborn
pip install .

# pip uninstall pypmt -y
# pip install git+https://github.com/pyPMT/pyPMT.git@d44efb71746b3a91e7fb1926b4405bd14f9df33b

mkdir -p $(pwd)/sandbox-benchmark/classical-domains
git clone --recursive https://github.com/AI-Planning/classical-domains.git $(pwd)/sandbox-benchmark/classical-domains
git clone --recursive https://github.com/pyPMT/numeric-domains.git $(pwd)/sandbox-benchmark/numeric-domains

python $(pwd)/paper_experiments/generate-benchmark-slurm-tasks.py --planning-type classical        --sandbox-dir $(pwd)/sandbox-benchmark-classical        --planning-tasks-dir $(pwd)/sandbox-benchmark/classical-domains/classical --resources-dir $(pwd)/paper_experiments/data/classical-domains-ru-info
python $(pwd)/paper_experiments/generate-benchmark-slurm-tasks.py --planning-type oversubscription --sandbox-dir $(pwd)/sandbox-benchmark-oversubscription --planning-tasks-dir $(pwd)/sandbox-benchmark/classical-domains/classical
python $(pwd)/paper_experiments/generate-benchmark-slurm-tasks.py --planning-type numerical        --sandbox-dir $(pwd)/sandbox-benchmark-numerical        --planning-tasks-dir $(pwd)/sandbox-benchmark/numeric-domains             --resources-dir $(pwd)/paper_experiments/data/functions-domains-info

sh $(pwd)/paper_experiments/split-slurm.sh $(pwd)/sandbox-benchmark-classical/slurm-dumps $(pwd)/sandbox-benchmark-classical/splitted-slurm-dumps classical $slurmpartname
sh $(pwd)/paper_experiments/split-slurm.sh $(pwd)/sandbox-benchmark-oversubscription/slurm-dumps $(pwd)/sandbox-benchmark-oversubscription/splitted-slurm-dumps osp $slurmpartname
sh $(pwd)/paper_experiments/split-slurm.sh $(pwd)/sandbox-benchmark-numerical/slurm-dumps $(pwd)/sandbox-benchmark-numerical/splitted-slurm-dumps numeric $slurmpartname
deactivate
