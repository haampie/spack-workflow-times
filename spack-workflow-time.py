from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
import sys
import hashlib
import os
import argparse
import re

GITHUB_URL = "https://api.github.com/repos/spack/spack"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
CACHE_PATH = ".cache"
WORKFLOW_RUNS = os.path.join(CACHE_PATH, "workflow_runs.json")


def default_headers():
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}"
    }

def created_extrema(workflows):
    min_created_at, max_created_at = None, None
    for workflow in workflows:
        created_at = datetime.fromisoformat(workflow["created_at"])
        min_created_at = created_at if min_created_at is None else min(created_at, min_created_at)
        max_created_at = created_at if max_created_at is None else max(created_at, max_created_at)
    return min_created_at, max_created_at


def get_workflows(min_date, max_date):
    # Read cached results.
    try:
        with open(WORKFLOW_RUNS, "r") as f:
            workflow_runs = json.load(f)
            curr_min, curr_max = created_extrema(workflow_runs.values())
    except OSError:
        workflow_runs = {}

    def fetch_between(min, max):
        page = 1
        while True:
            url = f'{GITHUB_URL}/actions/runs?branch=develop&status=completed&per_page=100&page={page}&created={min.date().isoformat()}..{max.date().isoformat()}'
            print(url, file=sys.stderr)
            workflows = json.loads(urlopen(Request(url, headers=default_headers(), method="GET")).read())
            for run in workflows["workflow_runs"]:
                workflow_runs[run["id"]] = run
            if len(workflows["workflow_runs"]) < 100:
                break
            curr_min, _ = created_extrema(workflows["workflow_runs"])
            # Github somehow is unhappy about jumping many pages, so after 9 pages,
            # switch to a new max date.
            if page < 9 or curr_min.date() == max.date():
                page += 1
            else:
                page = 1
                max = curr_min

        with open(WORKFLOW_RUNS, "w") as f:
            json.dump(workflow_runs, f)


    if not workflow_runs:
        fetch_between(min_date, max_date)
    else:
        if curr_max < max_date:
            fetch_between(curr_max, max_date)
        
        if curr_min > min_date:
            fetch_between(min_date, curr_min)
    
    return workflow_runs

def get_time(jobs, job_name: re.Pattern, step_name: re.Pattern):
    job = next((j for j in jobs["jobs"] if job_name.search(j["name"])), None)
    if not job:
        return None
    step = next((s for s in job["steps"] if step_name.search(s["name"])), None)
    if not step or step["conclusion"] != "success":
        return None
    started_at = datetime.fromisoformat(step["started_at"])
    completed_at = datetime.fromisoformat(step["completed_at"])
    return job["id"], started_at, completed_at


def get_all_times(workflows, job_name: re.Pattern, step_name: re.Pattern):
    urls = [w["jobs_url"] for w in workflows.values()]

    for i, url in enumerate(urls):
        url_hash = hashlib.md5(url.encode()).hexdigest()
        cache_name = os.path.join(CACHE_PATH, f"{url_hash}.json")

        # Cache or GET.
        if os.path.exists(cache_name):
            with open(cache_name, "r") as f:
                jobs = json.load(f)
        else:
            print(i, url, file=sys.stderr)
            jobs = json.loads(urlopen(Request(url, headers=default_headers(), method="GET")).read())
            with open(cache_name, "w") as f:
                json.dump(jobs, f)

        times = get_time(jobs, job_name=job_name, step_name=step_name)
        if times is None:
            continue
        job_id, started_at, completed_at = times
        timestamp, duration = started_at.timestamp(), (completed_at - started_at).seconds
        print(f"{job_id}\t{timestamp}\t{duration}", flush=True)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--update", help="Download workflows", action="store_true")
    parser.add_argument("-j", "--job-name", help="Regex for job name", action="store", default="clingo-cffi")
    parser.add_argument("-s", "--step-name", help="Regex for step name", action="store", default="Run unit tests")
    parser.add_argument("--since", help="yyyy-mm-dd format start date", action="store", default="2022-01-01")
    parser.add_argument("--github-token", help="GitHub token, initialized with GITHUB_TOKEN environment variable", action="store")
    args = parser.parse_args()

    if not os.path.isdir(CACHE_PATH):
        os.mkdir(CACHE_PATH)

    if args.github_token:
        GITHUB_TOKEN = args.github_token
    try:
        if args.update:
            min_date = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            get_workflows(
                min_date=min_date,
                max_date=datetime.now(timezone.utc)
            )

        try:
            with open(WORKFLOW_RUNS, "r") as f:
                workflows = json.load(f)
        except OSError:
            print("Run with --update to get the latest workflows.")
            exit(1)

        job_name = re.compile(args.job_name)
        step_name = re.compile(args.step_name)
        get_all_times(workflows, job_name=job_name, step_name=step_name)
    except HTTPError as e:
        if e.code == 401:
            print("Provide a github token: set GITHUB_TOKEN or pass --github-token")
            exit(1)
        raise