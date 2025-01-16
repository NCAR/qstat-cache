#!/usr/bin/env python3

import json, collections, argparse, sys, re

from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE,SIG_DFL) 

parser = argparse.ArgumentParser()
parser.add_argument("input_file")
parser.add_argument("--jobs", "-j", nargs='*')
parser.add_argument("--filter", "-J", action = "store_true")
parser.add_argument("--queues", "-q", nargs='*')
parser.add_argument("--status", "-s")
parser.add_argument("--arrays", "-t", action = "store_true")
parser.add_argument("--user", "-u")
args = parser.parse_args()

with open(args.input_file, 'r') as f:
    try:
        data = json.load(f, object_pairs_hook=collections.OrderedDict, strict = False)
    except json.decoder.JSONDecodeError:
        sys.exit(3)

if args.jobs:
    jobs = []
    for job in args.jobs:
        if "." in job:
            jobs.append(job)
        else:
            jobs.append("{}\.".format(job))

    try:
        data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if any([re.match(jid, job) for jid in jobs]) }
    except:
        sys.exit(3)

if args.queues:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if data['Jobs'][job]['queue'] in args.queues }

if args.user:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if data['Jobs'][job]['Job_Owner'].startswith("{}@".format(args.user)) }

if args.status:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if data['Jobs'][job]['job_state'] == args.status }

if args.arrays:
    if args.filter:
        data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if "array_index" in data['Jobs'][job] }
else:
    data['Jobs'] = { job : data['Jobs'][job] for job in data['Jobs'].keys() if "array_index" not in data['Jobs'][job] }

print(json.dumps(data, indent = 4))
