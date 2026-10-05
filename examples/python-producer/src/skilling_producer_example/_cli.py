"""Explicit local producer setup; credentials belong to the server's provider environment."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from skilling_tutor import TutorError

from ._app import create_app, validate_bind
from ._controller import ProducerController
from ._tutor import BrowserTutor


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local Welcome tutor")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--workspace", type=Path, required=True)
    serve.add_argument("--course", default="welcome-skilling")
    serve.add_argument("--model", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        validate_bind(args.host, args.port)
        runner = BrowserTutor.create(args.model)
        controller = ProducerController.open(args.workspace, runner, course_id=args.course)
    except (ValueError, OSError, TutorError) as error:
        parser.error(str(error))
    app = create_app(controller, host=args.host, port=args.port)
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
