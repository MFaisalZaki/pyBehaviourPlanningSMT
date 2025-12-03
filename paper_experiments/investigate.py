from collections import Counter
from analyser import read_raw_results
results_dir = '/Users/mustafafaisal/Developer/pyBehaviourPlanningSMT/sandbox-benchmark-numerical/resultsdir'


raw_results = read_raw_results(results_dir)

q_2_k_5  = list(filter(lambda x: x['q'] == 2 and x['k'] == 5  and x['planner'] == 'fbi-smt', raw_results))
q_2_k_10 = list(filter(lambda x: x['q'] == 2 and x['k'] == 10 and x['planner'] == 'fbi-smt', raw_results))

difference_instances = set((e['domain'], e['instance']) for e in q_2_k_10) - set((e['domain'], e['instance']) for e in q_2_k_5)

pass
