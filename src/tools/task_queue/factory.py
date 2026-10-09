from .interface import TaskQueue


def task_queue_factory(
    *,
    project_id: str,
    location: str,
    queue_name: str,
    backend_url: str,
    service_account_email: str,
    provider: str = "google",
    client=None,
) -> TaskQueue:
    if provider != "google":
        raise ValueError(f"Unsupported task queue provider: {provider}")

    from .google import GoogleTaskQueue

    return GoogleTaskQueue(
        project_id=project_id,
        location=location,
        queue_name=queue_name,
        backend_url=backend_url,
        service_account_email=service_account_email,
        client=client,
    )
