import os
from collections import defaultdict

import time

from .config import config

def log(message, level):
    logger = config.get("logger")
    if level == 0:
        logger.critical(message)
    elif level == 1:
        logger.error(message)
    elif level == 2:
        logger.warning(message)
    elif level == 3:
        logger.info(message)
    elif level >= 4:
        logger.debug(message)

def timethis(level):
    """ Decorator to allow to cleanly time functions """
    def inner_decorator(f):
        def wrapped(*args, **kwargs):
            start_time = time.time()  # Record the start time
            res = f(*args, **kwargs)
            end_time = time.time()  # Record the end time
            time_elapsed = end_time - start_time  # Calculate time elapsed for this iteration
            log(f"{f.__module__}:{f.__name__}: {round(time_elapsed,2)}s", level)
            return res
        return wrapped
    return inner_decorator

def compute_behaviour_space_statistics_smt(_diverseplans, _bspace):
    retstats = defaultdict(dict)

    #plansdetails = []    
    #for _, plan in enumerate(_diverseplans):
    #    plansdetails.append({f'{plan.id}': {'plan': str(plan), 'behaviour': str(plan.behaviour), 'actions-seq-plan': plan.actions_sequence}})

    retstats['dims-domains'] = defaultdict(dict)
    for name, _dim in _bspace.dims.items():
        if isinstance(_dim.var_domain, defaultdict):
            for key, value in _dim.var_domain.items():
                if isinstance(value, set):
                    retstats['dims-domains'][_dim.name][key] = list(value)
                else:
                    retstats['dims-domains'][_dim.name][key] = value
        elif isinstance(_dim.var_domain, set):
            retstats['dims-domains'][_dim.name] = list(_dim.var_domain)
        else:
            retstats['dims-domains'][_dim.name] = list(_dim.var_domain)
        

    #retstats['plans-details'] = plansdetails
    retstats['bspace-stats']  = _bspace._behaviour_frequency
    retstats['sat-time']      = _bspace.sat_time
    return retstats