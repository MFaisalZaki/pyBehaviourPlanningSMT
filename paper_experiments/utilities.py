import json

def getkeyvalue(data, target_key):
    if isinstance(data, dict):
        if target_key in data:
            return data[target_key]
        for value in data.values():
            result = getkeyvalue(value, target_key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = getkeyvalue(item, target_key)
            if result is not None:
                return result
    return None

def read_json_file(filepath):
    with open(filepath, 'r') as file:
        return json.load(file)


def construct_results_file(taskdetails, task, plans):
    from unified_planning.io import PDDLWriter
    import os
    task_writer = PDDLWriter(task)
    resultsfile = {
        'plans': [task_writer.get_plan(p) + f';{len(p.actions)} cost (unit)' + f'\n;behaviour: {p.behaviour.replace("\n","")}' for p in plans],
        'diversity-scores': {
            'behaviour-count': len(set(p.behaviour for p in plans))
        },
        'info' : {
            'domain' : os.path.basename(os.path.dirname(taskdetails['domainfile-name'])) + '/' + os.path.basename(taskdetails['domainfile-name']),
            'problem': os.path.basename(taskdetails['problemfile-name']),
            'planner': taskdetails['planner'],
            'tag' : taskdetails['planner'],
            'planning-type': taskdetails['planning-type'],
            'k': taskdetails['k-plans'],
            'q': taskdetails['q']
        },
    }
    return resultsfile

def add_utility_values(task):
    import unified_planning as up
    from unified_planning.model.walkers.free_vars import FreeVarsExtractor
    vars = next(map(lambda expr: FreeVarsExtractor().get(expr), task.goals), None)
    if vars is None: return {}
    goals = {g: (i+1)*2 for i, g in enumerate(vars)}
    task.add_quality_metric(up.model.metrics.Oversubscription(goals, task.environment))
    task.goals.clear()
    setattr(task, '_oversubscription_goals', task.goals[:])
    return goals
