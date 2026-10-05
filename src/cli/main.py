import argparse
import asyncio
import sys
from pathlib import Path

from runtime.factory import classifier_factory


async def print_events(classifier, document: bytes, filename: str) -> None:
    async for event in classifier.events(document, filename=filename):
        print(event.model_dump_json(), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify a PDF statement.")

    parser.add_argument("file", type=Path)

    parser.add_argument(
        "--stream", action="store_true", help="Print progress as JSON lines."
    )

    args = parser.parse_args()

    try:
        document = args.file.read_bytes()

        classifier = classifier_factory()

        if args.stream:
            asyncio.run(print_events(classifier, document, args.file.name))

        else:
            result = classifier.classify(document, filename=args.file.name)

            print(result.model_dump_json(indent=2))

    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)

        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
