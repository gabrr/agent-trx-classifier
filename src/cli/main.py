import argparse
import asyncio
import sys
from pathlib import Path

from tools.event_stream import workflow_events
from tools.statement_file import StatementFileInput
from workflows.trx_classifier.models import NormalizedStatement
from workflows.trx_classifier.workflow import build_workflow


async def print_events(workflow, file: StatementFileInput) -> None:
    parts = workflow.astream(
        {"file": file},
        config={"run_name": "trx_classifier"},
        stream_mode=["custom", "updates"],
        version="v2",
    )

    async for event in workflow_events(parts):
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

        workflow = build_workflow()

        if args.stream:
            asyncio.run(print_events(workflow, file))

        else:
            state = workflow.invoke(
                {"file": file}, config={"run_name": "trx_classifier"}
            )

            result = NormalizedStatement.model_validate(state["result"])

            print(result.model_dump_json(indent=2))

    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)

        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
