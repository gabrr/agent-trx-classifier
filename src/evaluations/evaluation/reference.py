import json
from copy import deepcopy
from pathlib import Path

DATASET_DIRECTORY = Path(__file__).resolve().parents[1] / "dataset"
DATASET_NAME = "trx-classifier"
LABEL_MAPPING = {"excluded": "movements", "installment": "installments"}


def load_definition() -> dict:
    return json.loads((DATASET_DIRECTORY / "dataset.json").read_text())


def reference_output(definition: dict) -> dict:
    reference = deepcopy(definition["reference_output"])

    for transaction in reference["transactions"]:
        label = transaction["report_bucket"]
        transaction["report_bucket"] = LABEL_MAPPING.get(label, label)

    return reference
