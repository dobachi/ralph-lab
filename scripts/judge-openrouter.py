#!/usr/bin/env python3
"""OpenRouter judge wrapper — simple prompt-in/response-out CLI for LLM-as-judge.

Usage:
    echo "your prompt" | judge-openrouter.py --model openai/gpt-4o
    # or: cat prompt.txt | judge-openrouter.py --model anthropic/claude-sonnet-4.5

Reads:
    - stdin: the prompt (user message)
    - env var: OPENROUTER_API_KEY (required)

Writes:
    - stdout: the model's text response (choices[0].message.content)
    - stderr: on error, a diagnostic message
    - exit code: 0 on success, non-zero on any failure

Design intent (P16 for ralph-lab):
    ralph-lab's spec.post_evaluation.cmd can be ANY executable. This lets
    us plug in OpenAI / other providers via OpenRouter without adding a
    dependency to ralph-lab core. Uses stdlib only (urllib + json).

    Matches the contract of `claude -p --dangerously-skip-permissions`
    from ralph-lab's perspective: stdin → prompt, stdout → response.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = "openai/gpt-4o"
API_URL = "https://openrouter.ai/api/v1/chat/completions"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenRouter judge wrapper")
    parser.add_argument(
        "--model",
        default=os.environ.get("JUDGE_MODEL", DEFAULT_MODEL),
        help=f"OpenRouter model ID (default: {DEFAULT_MODEL}, env: JUDGE_MODEL)",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=180.0,
        help="HTTP timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1000,
        help="max_tokens for the response (default: 1000)",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY env var is required", file=sys.stderr)
        return 2

    prompt = sys.stdin.read()
    if not prompt.strip():
        print("ERROR: empty stdin (no prompt)", file=sys.stderr)
        return 3

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": args.max_tokens,
    }
    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # HTTP-Referer & X-Title are optional metadata OpenRouter uses for
            # attribution — safe to include, harmless if omitted.
            "HTTP-Referer": "https://github.com/dobachi/ralph-lab",
            "X-Title": "ralph-lab-judge",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=args.timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"HTTPError {e.code}: {detail[:500]}", file=sys.stderr)
        return 4
    except urllib.error.URLError as e:
        print(f"URLError: {e.reason}", file=sys.stderr)
        return 5
    except TimeoutError:
        print(f"Timeout after {args.timeout_sec}s", file=sys.stderr)
        return 6

    choices = data.get("choices")
    if not choices:
        print(f"ERROR: no choices in response: {json.dumps(data)[:500]}", file=sys.stderr)
        return 7

    content = choices[0].get("message", {}).get("content", "")
    print(content, end="")  # No trailing newline — content itself may or may not have one
    return 0


if __name__ == "__main__":
    sys.exit(main())
