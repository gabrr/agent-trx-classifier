from langsmith import Client

from runtime.settings import load_environment

from .reference import (
    DATASET_DIRECTORY,
    DATASET_NAME,
    load_definition,
    reference_output,
)


def sync_dataset(client: Client | None = None) -> str:
    load_environment()

    client = client or Client()

    definition = load_definition()

    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)

    else:
        dataset = client.create_dataset(
            DATASET_NAME,
            description="Full PDF to transactions; parallel explicit categories.",
        )

    fixture = DATASET_DIRECTORY / "fixtures" / definition["input"]["fixture"]
    example = {
        "inputs": definition["input"],
        "outputs": reference_output(definition),
        "attachments": {
            "statement": {"mime_type": "application/pdf", "data": fixture.read_bytes()}
        },
        "metadata": {"dataset_id": definition["dataset_id"]},
    }
    existing = list(
        client.list_examples(
            dataset_id=dataset.id,
            metadata={"dataset_id": definition["dataset_id"]},
            limit=1,
        )
    )

    if existing:
        client.update_examples(
            dataset_id=dataset.id, updates=[{"id": existing[0].id, **example}]
        )

    else:
        client.create_examples(dataset_id=dataset.id, examples=[example])

    return DATASET_NAME


def main() -> None:
    print(f"Synchronized LangSmith dataset: {sync_dataset()}")


if __name__ == "__main__":
    main()
