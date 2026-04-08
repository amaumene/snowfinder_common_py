"""Shared CLI runner for snowfinder services.

Usage::

    from snowfinder_common.cli import run_service
    from myservice.database import Database
    from myservice.pipeline import run_pipeline

    if __name__ == "__main__":
        run_service("myservice", run_pipeline, db_class=Database)

    # With extra CLI arguments:
    def setup_parser(parser):
        parser.add_argument("--extract-msm", action="store_true")

    run_service("analyzer", run_pipeline, db_class=Database, setup_parser=setup_parser)
"""

import argparse
import logging
import os
import sys
import time
from collections.abc import Callable

from dotenv import load_dotenv

from .database import Database as _BaseDatabase
from .logging_config import configure_logging

logger = logging.getLogger(__name__)


def run_service(
    service_name: str,
    pipeline_fn: Callable[..., None],
    *,
    db_class: type[_BaseDatabase] = _BaseDatabase,
    setup_parser: Callable[[argparse.ArgumentParser], None] | None = None,
) -> None:
    """Run a snowfinder service pipeline from the command line.

    Parameters
    ----------
    service_name:
        Human-readable service name for help text and logging.
    pipeline_fn:
        Pipeline function accepting ``(db, args)``.  The ``args`` namespace
        contains at least ``verbose`` and ``database_url``, plus any extra
        arguments registered via *setup_parser*.
    db_class:
        Database subclass to instantiate (default: common ``Database``).
    setup_parser:
        Optional callback to register extra CLI arguments on the
        ``ArgumentParser`` before ``parse_args()`` is called.
    """
    load_dotenv()

    parser = argparse.ArgumentParser(description=f"SnowFinder {service_name.title()}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL connection URL",
    )

    if setup_parser is not None:
        setup_parser(parser)

    args = parser.parse_args()

    configure_logging(verbose=args.verbose)

    if not args.database_url:
        logger.error("DATABASE_URL is required (env var or --database-url flag)")
        sys.exit(1)

    start = time.time()

    try:
        with db_class(args.database_url) as db:
            pipeline_fn(db, args)
    except Exception as e:
        logger.error("%s failed: %s", service_name.title(), e, exc_info=True)
        sys.exit(1)

    elapsed = time.time() - start
    logger.info("%s completed in %.1fs", service_name.title(), elapsed)
