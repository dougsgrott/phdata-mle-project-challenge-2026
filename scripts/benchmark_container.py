"""Benchmark a built API image under fixed resource limits (1 CPU, 2 GB).

For one image it records:
  * image size
  * cold start: time from `docker run` until /health answers, plus the latency of
    the first /predict request, repeated on fresh containers (median reported)
  * load results from send_examples.py at concurrency 1 and 10 on a warm container
  * a `docker stats` snapshot taken right after the load runs

Everything is merged into reports/benchmark/<label>.json. The container is always
removed afterwards, even on failure.
"""

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from send_examples import DEFAULT_INPUT, load_rows

ROOT = Path(__file__).resolve().parent.parent
SEND_EXAMPLES = ROOT / "scripts" / "send_examples.py"
CONTAINER = "housing-api-benchmark"
CPUS = "1"
MEMORY = "2g"
CONTAINER_PORT = 8000
CONCURRENCY_LEVELS = (1, 10)


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        sys.exit(f"docker {' '.join(args)} failed ({proc.returncode}):\n{proc.stderr.strip()}")
    return proc


def remove_container() -> None:
    docker("rm", "-f", CONTAINER, check=False)


def start_and_wait(args: argparse.Namespace) -> float:
    """Start a fresh container; return seconds until /health answers 200."""
    remove_container()
    cmd = [
        "run", "-d", "--name", CONTAINER,
        "--cpus", CPUS, "--memory", MEMORY,
        "-p", f"{args.port}:{CONTAINER_PORT}",
    ]  # fmt: skip
    for volume in args.volume:
        cmd += ["-v", volume]
    cmd.append(args.image)

    start = time.perf_counter()
    docker(*cmd)
    url = f"http://localhost:{args.port}/health"
    while time.perf_counter() - start < args.health_timeout:
        try:
            if httpx.get(url, timeout=1.0).status_code == 200:
                return time.perf_counter() - start
        except httpx.HTTPError:
            pass
        time.sleep(0.05)

    logs = docker("logs", "--tail", "30", CONTAINER, check=False)
    sys.exit(
        f"/health did not answer within {args.health_timeout}s\n"
        f"{logs.stdout}{logs.stderr}"
    )


def timed_first_request(url: str, payload: dict) -> float:
    start = time.perf_counter()
    response = httpx.post(f"{url}/predict", json=payload, timeout=30.0)
    elapsed = time.perf_counter() - start
    response.raise_for_status()
    return elapsed * 1000


def run_load(url: str, concurrency: int, args: argparse.Namespace) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "report.json"
        proc = subprocess.run(
            [
                sys.executable, str(SEND_EXAMPLES),
                "--url", url,
                "--input", str(args.input),
                "--concurrency", str(concurrency),
                "--label", f"{args.label}-c{concurrency}",
                "--report", str(report_path),
            ],
            capture_output=True,
            text=True,
        )  # fmt: skip
        if not report_path.exists():
            sys.exit(f"send_examples.py produced no report:\n{proc.stderr}")
        return json.loads(report_path.read_text())


def docker_stats() -> dict:
    out = docker("stats", "--no-stream", "--format", "{{json .}}", CONTAINER)
    return json.loads(out.stdout.strip())


def image_size_bytes(image: str) -> int:
    out = docker("image", "inspect", "--format", "{{.Size}}", image)
    return int(out.stdout.strip())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", required=True, help="e.g. housing-api:baseline")
    p.add_argument("--label", required=True, help="report name, e.g. baseline")
    p.add_argument("--cold-starts", type=int, default=3)
    p.add_argument("--port", type=int, default=8000, help="host port to publish on")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--health-timeout", type=float, default=60.0)
    p.add_argument(
        "--volume", action="append", default=[],
        help="extra `docker run -v` mount, repeatable (e.g. ./src/model:/app/model:ro)",
    )  # fmt: skip
    args = p.parse_args()
    if args.cold_starts < 1:
        p.error("--cold-starts must be >= 1")

    url = f"http://localhost:{args.port}"
    payload = load_rows(args.input)[0]
    cold_runs: list[dict] = []
    load: dict = {}

    try:
        for i in range(args.cold_starts):
            health_s = start_and_wait(args)
            first_ms = timed_first_request(url, payload)
            cold_runs.append({"health_seconds": health_s, "first_request_ms": first_ms})
            print(
                f"cold start {i + 1}/{args.cold_starts}: "
                f"health {health_s:.2f}s, first request {first_ms:.0f} ms"
            )
            if i < args.cold_starts - 1:
                remove_container()

        # The last container is now warm: use it for the load runs.
        for c in CONCURRENCY_LEVELS:
            print(f"load run: concurrency {c}")
            load[f"c{c}"] = run_load(url, c, args)
        stats = docker_stats()
    finally:
        remove_container()

    size = image_size_bytes(args.image)
    report = {
        "label": args.label,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "image": args.image,
        "image_size_bytes": size,
        "image_size_mb": round(size / 1e6, 1),
        "limits": {"cpus": CPUS, "memory": MEMORY},
        "cold_start": {
            "runs": cold_runs,
            "median_health_seconds": statistics.median(
                r["health_seconds"] for r in cold_runs
            ),
            "median_first_request_ms": statistics.median(
                r["first_request_ms"] for r in cold_runs
            ),
        },
        "load": load,
        "docker_stats": stats,
    }

    out = ROOT / "reports" / "benchmark" / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {out}")

    failed = sum(r["failed"] for r in load.values())
    if failed:
        print(f"WARNING: {failed} requests failed during load runs", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
