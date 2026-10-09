from .interface import ObjectStorage


def object_storage_factory(
    *, bucket_name: str, provider: str = "google", client=None
) -> ObjectStorage:
    if provider != "google":
        raise ValueError(f"Unsupported object storage provider: {provider}")

    from .google import GoogleObjectStorage

    return GoogleObjectStorage(bucket_name=bucket_name, client=client)
