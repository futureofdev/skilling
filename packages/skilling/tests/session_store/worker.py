"""Subprocess operations synchronized by their parent's pipes, without timing races."""

from __future__ import annotations

import sys
from pathlib import Path

from skilling.store import FileSessionStore, StoreError


def main() -> None:
    root = Path(sys.argv[1])
    namespace = sys.argv[2]
    print("ready", flush=True)
    if sys.stdin.readline().strip() != "go":
        raise RuntimeError("Missing parent release")
    try:
        FileSessionStore.open(root, namespace=namespace, learner_id="same-learner")
    except (StoreError, ValueError):
        print("refused", flush=True)
    else:
        print("bound", flush=True)


if __name__ == "__main__":
    main()
