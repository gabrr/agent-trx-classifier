import argparse
import asyncio
import sys
from pathlib import Path

from runtime.factory import classifier_factory
from tools.statement_file import StatementFileInput


async def print_events(classifier, file: StatementFileInput) -> None:
    async for event in classifier.events(file):
        print(event.model_dump_json(), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify a PDF or CSV statement.")

    parser.add_argument("file", type=Path)

    parser.add_argument(
        "--stream", action="store_true", help="Print progress as JSON lines."
    )

    args = parser.parse_args()

    try:
        document = args.file.read_bytes()

        file = StatementFileInput.from_bytes(document, filename=args.file.name)

        classifier = classifier_factory()

        if args.stream:
            asyncio.run(print_events(classifier, file))

        else:
            result = classifier.classify(file)

            print(result.model_dump_json(indent=2))

    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)

        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
