"""Entrypoint. Run with no args for the polling loop, or --daily-sweep for the audit."""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-sweep", action="store_true",
                        help="Run the feedback sweep once and exit (used by scheduled cron).")
    args = parser.parse_args()

    tenants_root = Path(__file__).resolve().parent / "tenants"
    tenant_name = os.getenv("TENANT_NAME", "shine")

    if args.daily_sweep:
        from shine_email_assistant.db import init_db
        from shine_email_assistant.feedback import audit_recent_drafts
        from shine_email_assistant.log import configure_logging
        configure_logging()
        init_db()
        audit_recent_drafts()
        return 0

    from shine_email_assistant.pipeline import run_forever
    poll = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    run_forever(tenant_name=tenant_name, tenants_root=tenants_root, poll_interval_seconds=poll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
