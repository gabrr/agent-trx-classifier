from .interface import JobService


def job_service_factory(
    sessions,
    storage,
    queue,
    settings,
    *,
    provider: str = "postgres",
    classifier_factory=None,
) -> JobService:
    if provider != "postgres":
        raise ValueError(f"Unsupported job service: {provider}")

    from .postgres import PostgresJobService

    return PostgresJobService(
        sessions, storage, queue, settings, classifier_factory=classifier_factory
    )
