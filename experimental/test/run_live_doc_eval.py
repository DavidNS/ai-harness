"""Manual live A/B runner for architecture-document understanding.

This script is intentionally outside production tests. It spends provider tokens
only when invoked directly.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from doc_understanding_cases import CASES, READING_GUIDE, DocUnderstandingCase


ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "ARCHITECTURE.md"
RESULTS = Path(__file__).resolve().parent / "results"
TOKEN_EVAL_ENV = "AI_HARNESS_ALLOW_TOKEN_EVAL"


def _enforce_token_guard(args: argparse.Namespace) -> None:
    if not args.spend_tokens:
        raise SystemExit(
            "live doc eval spends provider tokens; rerun with --spend-tokens "
            f"and {TOKEN_EVAL_ENV}=1"
        )
    if os.environ.get(TOKEN_EVAL_ENV) != "1":
        raise SystemExit(f"set {TOKEN_EVAL_ENV}=1 to allow token-spending evals")
    if os.environ.get("CI") and not args.allow_ci:
        raise SystemExit("live doc eval is disabled in CI; rerun with --allow-ci only intentionally")


def _provider_command(provider: str, prompt: str) -> list[str]:
    if provider == "codex":
        return ["codex", "exec", prompt]
    if provider == "claude":
        return ["claude", "--print", prompt]
    raise ValueError(f"unsupported provider: {provider}")


def _run_provider(provider: str, prompt: str, timeout_seconds: int) -> dict[str, object]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            _provider_command(provider, prompt),
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        timed_out = False
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        exit_code = None

    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def _score(case: DocUnderstandingCase, output: str) -> dict[str, object]:
    normalized = output.lower()
    required_hits = [
        term for term in case.required_terms
        if term.lower() in normalized
    ]
    forbidden_hits = [
        term for term in case.forbidden_terms
        if term.lower() in normalized
    ]
    overview_authority = (
        "overview" in normalized
        or "system map" in normalized
        or "not a low-level" in normalized
    )

    return {
        "required_hits": required_hits,
        "missing_required": [
            term for term in case.required_terms
            if term.lower() not in normalized
        ],
        "forbidden_hits": forbidden_hits,
        "overview_authority": overview_authority,
        "passed": (
            len(required_hits) == len(case.required_terms)
            and not forbidden_hits
            and overview_authority
        ),
    }


def _variant_document(name: str, architecture_text: str) -> str:
    if name == "current":
        return architecture_text
    if name == "reading-guide":
        return f"{READING_GUIDE}\n\n{architecture_text}"
    raise ValueError(f"unsupported variant: {name}")


def _prompt(case: DocUnderstandingCase, document: str) -> str:
    return (
        "Answer from the architecture document below. Treat it as an overview, "
        "not as a low-level implementation contract. Do not invent APIs.\n\n"
        f"ARCHITECTURE.md:\n{document}\n\n"
        f"Task:\n{case.prompt}\n"
    )


def _selected_cases(selected: str) -> tuple[DocUnderstandingCase, ...]:
    if selected == "all":
        return CASES
    requested = {item.strip() for item in selected.split(",") if item.strip()}
    cases = tuple(case for case in CASES if case.case_id in requested)
    missing = requested - {case.case_id for case in cases}
    if missing:
        raise SystemExit(f"unknown case id(s): {', '.join(sorted(missing))}")
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("codex", "claude"), default="codex")
    parser.add_argument("--cases", default="all")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument(
        "--spend-tokens",
        action="store_true",
        help=f"allow provider calls; also requires {TOKEN_EVAL_ENV}=1",
    )
    parser.add_argument(
        "--allow-ci",
        action="store_true",
        help="allow live eval under CI after the token guard also passes",
    )
    args = parser.parse_args(argv)
    _enforce_token_guard(args)

    architecture_text = ARCHITECTURE.read_text(encoding="utf-8")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RESULTS.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS / f"{run_id}-{args.provider}.jsonl"

    with output_path.open("w", encoding="utf-8") as handle:
        for case in _selected_cases(args.cases):
            for variant in ("current", "reading-guide"):
                prompt = _prompt(case, _variant_document(variant, architecture_text))
                provider_result = _run_provider(args.provider, prompt, args.timeout_seconds)
                score = _score(case, str(provider_result["stdout"]))
                record = {
                    "run_id": run_id,
                    "provider": args.provider,
                    "variant": variant,
                    "case": asdict(case),
                    "score": score,
                    "provider_result": provider_result,
                }
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                status = "PASS" if score["passed"] else "FAIL"
                print(f"{status} {variant} {case.case_id}")

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
