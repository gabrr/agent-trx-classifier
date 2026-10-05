import json

from langsmith import Client

from runtime.factory import classifier_factory

from .dataset import sync_dataset
from .evaluators import EVALUATORS


def run_evaluation():
    classifier = classifier_factory()

    dataset_name = sync_dataset()

    def target(inputs: dict, attachments: dict) -> dict:
        document = attachments["statement"]["reader"].read()

        result = classifier.classify(document, filename=inputs["fixture"])

        return result.model_dump(mode="json")

    return Client().evaluate(
        target,
        data=dataset_name,
        evaluators=EVALUATORS,
        experiment_prefix="parallel-choice",
        max_concurrency=1,
        blocking=True,
    )


def main() -> None:
    results = run_evaluation()

    for row in results:
        feedback = row["evaluation_results"]["results"]
        print(json.dumps({item.key: item.score for item in feedback}))


if __name__ == "__main__":
    main()
