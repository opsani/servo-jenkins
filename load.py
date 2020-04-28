#!/usr/bin/env python3

from measure import Measure, ST_FAILED

import sys
import os
import time
from traceback import format_exc
import subprocess

from threading import Timer

import requests
import json
import yaml
from jenkinsapi.jenkins import Jenkins as JenkinsApi

DESC = "Jenkins load driver for Opsani Optune"
VERSION = "0.0.1"
HAS_CANCEL = True
PROGRESS_INTERVAL = 30

DEFAULT_CONFIGURATION = {
    "jenkins_secret_path": "/etc/opsani/jenkins/token",
    "jenkins_retry_timeout": 15,
    "jenkins_poll_interval": 15,
}

METRICS = {
    "time taken": {"unit": "seconds",},
}

config_path = os.environ.get("OPTUNE_CONFIG", "./config.yaml")


def get_config():
    try:
        with open(config_path) as f:
            config_from_file = yaml.safe_load(f)
        config = config_from_file.get("jenkins", {})
    except FileNotFoundError:
        config = {}

    config["jenkins_url"] = os.environ.get("JENKINS_URL", config.get("jenkins_url"))
    assert config.get("jenkins_url"), "Jenkins URL was not configured"

    config["jenkins_secret_path"] = (
        os.environ.get("JENKINS_SECRET_PATH", config.get("jenkins_secret_path"))
        or DEFAULT_CONFIGURATION["jenkins_secret_path"]
    )
    config["jenkins_token"] = os.environ.get(
        "JENKINS_TOKEN", config.get("jenkins_token")
    )
    if not config["jenkins_token"]:
        with open(config["jenkins_secret_path"]) as tok_file:
            config["jenkins_token"] = tok_file.read().strip()

    config["jenkins_user"] = os.environ.get("JENKINS_USER", config.get("jenkins_user"))
    assert config.get("jenkins_user"), "Jenkins user was not configured"

    config["jenkins_job"] = os.environ.get("JENKINS_JOB", config.get("jenkins_job"))
    assert config.get("jenkins_job"), "Jenkins job was not configured"

    config["jenkins_retry_timeout"] = (
        config.get("jenkins_retry_timeout")
        or DEFAULT_CONFIGURATION["jenkins_retry_timeout"]
    )
    config["jenkins_poll_interval"] = (
        config.get("jenkins_poll_interval")
        or DEFAULT_CONFIGURATION["jenkins_poll_interval"]
    )
    return config


class Jenkins(Measure):
    def __init__(self, version, cli_desc, supports_cancel, progress_interval):
        super().__init__(version, cli_desc, supports_cancel, progress_interval)

        self.load_queue_item = None

    # overwrites super
    def describe(self):
        return METRICS

    # overwrites super
    def handle_cancel(self, signal, frame):
        err = "Exiting due to signal: %s" % signal
        self.print_measure_error(err, ST_FAILED)

        if self.load_queue_item is not None:
            self.load_queue_item.get_build().stop()

        sys.exit(3)

    # overwrites super
    def measure(self):
        jenkins_cfg = get_config()
        load_cfg = self.input_data.get("control", {}).get("load", {})
        if not load_cfg:
            raise Exception(
                "Invalid control configuration format in input. Control found: {}".format(
                    self.input_data.get("control")
                )
            )

        jenkins_cfg["duration"] = f"{load_cfg['duration'] + load_cfg['warmup']}s"
        # TODO: duration doesn't go anywhere

        time_taken = self._run_jenkins(jenkins_cfg)

        metrics = {k: v.copy() for k, v in METRICS.items()}
        metrics["time taken"]["value"] = time_taken

        annotations = {}

        return (metrics, annotations)

    def _run_jenkins(self, config):
        self.progress = 0

        retry_timeout = config["jenkins_retry_timeout"]
        poll_interval = config["jenkins_poll_interval"]
        server = JenkinsApi(
            config["jenkins_url"], config["jenkins_user"], config["jenkins_token"]
        )
        job = server.get_job(config["jenkins_job"])

        is_running = _check_job(job, retry_timeout)

        if not is_running:
            # print("no load testing, starting")
            while True:
                try:
                    self.load_queue_item = job.invoke()
                except:
                    # print("Error: {} \n\nretrying api call".format(format_exc()), file=sys.stderr)
                    time.sleep(retry_timeout)
                    is_running = _check_job(job, retry_timeout)
                    if is_running:
                        break
                    continue
                is_running = True
                start_time = time.time()
                break
            time.sleep(poll_interval)
            # print("load testing started")

        if is_running:
            # print("load test running")
            while True:
                self.progress = min(100, int((time.time() - start_time) / config['duration']) * 100)
                is_running=_check_job(job, retry_timeout)
                if is_running:
                    pass  # print(f"still running\n   test again in {poll_interval} seconds")
                else:
                    break
                time.sleep(poll_interval)

        return time.time() - start_time


def _check_job(job, retry_timeout):
    while True:
        try:
            is_running = job.is_running()
        except:
            # print("Error: {} \n\nretrying api call".format(format_exc()), file=sys.stderr)
            time.sleep(retry_timeout)
            continue
        break
    return is_running


if __name__ == "__main__":
    jenkins = Jenkins(
        version=VERSION,
        cli_desc=DESC,
        supports_cancel=HAS_CANCEL,
        progress_interval=PROGRESS_INTERVAL,
    )
    jenkins.run()
