from collections import Counter
from analyser import read_raw_results
results_dir = '/home/ma342/developer/pyBehaviourPlanningSMT/sandbox-benchmark-oversubscription/resultsdir'


raw_results = read_raw_results(results_dir)

smt  = list(filter(lambda x: x['q'] == 0.25 and x['k'] == 5  and x['planner'] == 'fbi-smt', raw_results))
smtnaive = list(filter(lambda x: x['q'] == 0.25 and x['k'] == 5  and x['planner'] == 'fbi-smt-naive', raw_results))

smt_instances_unsolved = set((e['domain'], e['instance']) for e in filter(lambda e: len(e['plans']) > 0 and len(e['plans']) < e['k'], smt))

pass
