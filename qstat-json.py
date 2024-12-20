#!/usr/bin/env python3

import json, collections, argparse, sys

from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE,SIG_DFL) 

parser = argparse.ArgumentParser()
parser.add_argument("input_file")
parser.add_argument("--jobs", "-j", nargs='*')
parser.add_argument("--queues", "-q", nargs='*')
parser.add_argument("--status", "-s")
parser.add_argument("--user", "-u")
args = parser.parse_args()

with open(args.input_file, 'r') as f:
    try:
        data = json.load(f, object_pairs_hook=collections.OrderedDict)
    except json.decoder.JSONDecodeError:
        sys.exit(3)

if args.jobs:
    jobs = []
    for job in args.jobs:
        if "." in job:
            jobs.append(job)
        else:
            jobs.append("{}.".format(job))

    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if job.startswith(tuple(jobs)) }

if args.queues:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if data['Jobs'][job]['queue'] in args.queues }

if args.user:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if data['Jobs'][job]['Job_Owner'].startswith("{}@".format(args.user)) }

if args.status:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if data['Jobs'][job]['job_state'] == args.status }

print(json.dumps(data, indent = 4))
