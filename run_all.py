#!/usr/bin/env python3
"""
ERA Benchmark Suite Supervisor
Sequentially executes (SUBSET_NUMBER, RUN_NUMBER) sweeps with strict process isolation.
"""

import os
import sys
import time
import signal
import subprocess
from datetime import datetime
from pathlib import Path

# --- Experiment Grid Configuration ---
SUBSET_RANGE = range(0, 11)   # 0 to 10 inclusive (11 subsets)
RUN_RANGE = range(0, 3)        # 0 to 2 inclusive (3 runs each -> 33 total runs)
WORKER_SCRIPT = "curated_main.py"      # Your original execution script
COOLDOWN_SECONDS = 5           # Safety buffer for OS / ROCm driver to flush handles
SUPERVISOR_LOG = Path("benchmark_supervisor.log")


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    print(formatted, flush=True)
    with open(SUPERVISOR_LOG, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")


def run_command_isolated(cmd: list[str]) -> int:
    """
    Executes the command in a new process group.
    Ensures clean termination of all child threads/subprocesses if interrupted.
    """
    # preexec_fn=os.setsid assigns the child to a new process group
    proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
    
    try:
        return proc.wait()
    except KeyboardInterrupt:
        log("⚠️ Supervisor received KeyboardInterrupt. Propagating SIGTERM to worker process group...")
        try:
            # Kill the entire child process group cleanly
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=15)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        raise


def main():
    worker_path = Path(__file__).parent / WORKER_SCRIPT
    if not worker_path.is_file():
        sys.exit(f"❌ Error: Worker script not found at {worker_path}")

    total_tasks = len(SUBSET_RANGE) * len(RUN_RANGE)
    completed_tasks = 0
    failures = []

    log("=" * 70)
    log(f"STARTING SEQUENTIAL BENCHMARK CAMPAIGN: {total_tasks} TOTAL RUNS")
    log(f"Subsets: {list(SUBSET_RANGE)}")
    log(f"Runs per subset: {list(RUN_RANGE)}")
    log("=" * 70)

    for subset in SUBSET_RANGE:
        for run_idx in RUN_RANGE:
            completed_tasks += 1
            log("-" * 60)
            log(f"▶️ Task [{completed_tasks}/{total_tasks}]: Launching Subset={subset}, Run={run_idx}")
            
            cmd = [sys.executable, str(worker_path), str(subset), str(run_idx)]
            start_time = time.time()
            
            try:
                exit_code = run_command_isolated(cmd)
                elapsed_hours = (time.time() - start_time) / 3600.0

                if exit_code == 0:
                    log(f"✅ Completed Task [{completed_tasks}/{total_tasks}] (Subset={subset}, Run={run_idx}) in {elapsed_hours:.2f}h")
                else:
                    log(f"❌ FAILED Task [{completed_tasks}/{total_tasks}] (Subset={subset}, Run={run_idx}) with exit code {exit_code}")
                    failures.append((subset, run_idx, exit_code))

            except KeyboardInterrupt:
                log("🛑 Campaign aborted by operator.")
                sys.exit(1)
            
            # Cooldown buffer: yields CPU/GPU scheduling, allows network & VRAM driver cleanup
            time.sleep(COOLDOWN_SECONDS)

    log("=" * 70)
    log("CAMPAIGN COMPLETE")
    log(f"Total Successful: {total_tasks - len(failures)}/{total_tasks}")
    if failures:
        log(f"Failed Runs: {failures}")
    log("=" * 70)


if __name__ == "__main__":
    main()