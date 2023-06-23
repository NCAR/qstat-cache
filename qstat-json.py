#!/usr/bin/env python3

import json, collections, argparse

from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE,SIG_DFL) 

parser = argparse.ArgumentParser()
parser.add_argument("input_file")
parser.add_argument("--jobs", "-j", nargs='*')
parser.add_argument("--queues", "-q", nargs='*')
parser.add_argument("--user", "-u")
args = parser.parse_args()

with open(args.input_file, 'r') as f:
    data = json.load(f, object_pairs_hook=collections.OrderedDict)

if args.jobs:
    jobs = []
    for job in args.jobs:
        if "." in job:
            jobs.append(job)
        else:
            jobs.append("{}.".format(job))

    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if job.startswith(tuple(jobs)) }

if args.queues:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if data['Jobs'][job]['queue'] in args.queues) }

if args.user:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if data['Jobs'][job]['Job_Owner'].startswith("{}@".format(args.user)) }

print(json.dumps(data, indent = 4))
