"""mentor CLI: serve | job {morning,replan,compact} | doctor."""

import argparse

from mentor.app.config import Config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mentor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    job = sub.add_parser("job")
    job.add_argument("name", choices=["morning", "replan", "compact"])
    sub.add_parser("doctor")
    return parser


def _doctor() -> None:
    config = Config.from_env()
    print(f"data_dir: {config.data_dir}")
    print(f"tz: {config.tz}")
    print(f"telegram_bot_token: {'set' if config.telegram_bot_token else 'unset'}")
    print(f"telegram_chat_id: {'set' if config.telegram_chat_id else 'unset'}")
    print(f"claude_code_oauth_token: {'set' if config.claude_code_oauth_token else 'unset'}")


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "doctor":
        _doctor()
    else:
        print("not implemented")


if __name__ == "__main__":
    main()
