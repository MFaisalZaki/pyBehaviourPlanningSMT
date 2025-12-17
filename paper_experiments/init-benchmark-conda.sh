if [ $# -gt 0 ]; then
    slurmpartname=$1
else
    echo "Usage: $0 <slurmpartname>"
    exit 1
fi

condaenvname=behaviour_planning_smt

conda remove -n $condaenvname --all -y
conda create -n $condaenvname python=3.12 -y
conda init
source ~/.bash_profile
conda activate $condaenvname

python -m pip install setuptools
python -m pip install unified-planning
python -m pip install --no-cache up-symk
python -m pip install git+https://github.com/MFaisalZaki/forbiditerative.git
python -m pip install lark
python -m pip install up-fast-downward
python -m pip install matplotlib 
python -m pip install seaborn
python -m pip install .

mkdir -p $(pwd)/sandbox-benchmark/classical-domains
git clone --recursive https://github.com/AI-Planning/classical-domains.git $(pwd)/sandbox-benchmark/classical-domains
git clone --recursive https://github.com/pyPMT/numeric-domains.git $(pwd)/sandbox-benchmark/numeric-domains

python $(pwd)/paper_experiments/generate-benchmark-slurm-tasks.py --use-conda --conda-name $condaenvname --planning-type classical        --sandbox-dir $(pwd)/sandbox-benchmark-classical        --planning-tasks-dir $(pwd)/sandbox-benchmark/classical-domains/classical --resources-dir $(pwd)/paper_experiments/data/classical-domains-ru-info
python $(pwd)/paper_experiments/generate-benchmark-slurm-tasks.py --use-conda --conda-name $condaenvname --planning-type oversubscription --sandbox-dir $(pwd)/sandbox-benchmark-oversubscription --planning-tasks-dir $(pwd)/sandbox-benchmark/classical-domains/classical
python $(pwd)/paper_experiments/generate-benchmark-slurm-tasks.py --use-conda --conda-name $condaenvname --planning-type numerical        --sandbox-dir $(pwd)/sandbox-benchmark-numerical        --planning-tasks-dir $(pwd)/sandbox-benchmark/numeric-domains             --resources-dir $(pwd)/paper_experiments/data/functions-domains-info

sh $(pwd)/paper_experiments/split-slurm.sh $(pwd)/sandbox-benchmark-classical/slurm-dumps $(pwd)/sandbox-benchmark-classical/splitted-slurm-dumps classical $slurmpartname
sh $(pwd)/paper_experiments/split-slurm.sh $(pwd)/sandbox-benchmark-oversubscription/slurm-dumps $(pwd)/sandbox-benchmark-oversubscription/splitted-slurm-dumps osp $slurmpartname
sh $(pwd)/paper_experiments/split-slurm.sh $(pwd)/sandbox-benchmark-numerical/slurm-dumps $(pwd)/sandbox-benchmark-numerical/splitted-slurm-dumps numeric $slurmpartname
conda deactivate
