"""Serve the built reference UI with a loopback-only demo identity boundary."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles
from pydantic_ai import Agent

from .app import create_app
from .deployment.config import ProducerConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Skilling React tutor reference app")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Serve the built React UI and tutor API")
    serve.add_argument(
        "--config",
        type=Path,
        default=os.environ.get("TUTOR_CONFIG"),
        help="Absolute path to producer TOML configuration",
    )
    serve.add_argument(
        "--data-dir", type=Path, default=Path(os.environ.get("TUTOR_DATA_DIR", ".data"))
    )
    serve.add_argument(
        "--course",
        type=Path,
        default=os.environ.get("TUTOR_COURSE_DIR"),
        help="Welcome course directory (required if installed)",
    )
    serve.add_argument(
        "--model", required=True, help="Provider:model; credentials stay server-side"
    )
    serve.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1")
    serve.add_argument("--port", type=int, choices=range(1, 65536), metavar="PORT", default=8000)
    args = parser.parse_args()
    assets = Path(__file__).resolve().parent / "static"
    if not (assets / "index.html").is_file():
        assets = Path(__file__).resolve().parents[2] / "dist"
    if not (assets / "index.html").is_file():
        parser.error(
            "React assets are missing; run npm ci && npm run build in examples/react-tutor"
        )
    try:
        config = ProducerConfig.load(args.config.resolve()) if args.config else None
        app = create_app(
            agent=Agent(args.model),
            data_dir=args.data_dir.resolve(),
            config=config,
            course_path=args.course.resolve() if args.course else None,
            allowed_origins=tuple(
                f"http://{host}:{port}"
                for host in ("localhost", "127.0.0.1")
                for port in (args.port, 5173)
            ),
        )
    except (ValueError, OSError) as error:
        parser.error(f"Cannot start reference app: {type(error).__name__}; check paths and config")
    app.mount("/", StaticFiles(directory=assets, html=True), name="react")
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
