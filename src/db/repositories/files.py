from sqlalchemy import select

from db.models import UploadedFile


def create_file(
    session,
    owner_id,
    *,
    filename,
    content_type,
    size_bytes,
    storage_bucket,
    storage_object,
    storage_generation=None,
    checksum=None,
):
    file = UploadedFile(
        owner_id=owner_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_bucket=storage_bucket,
        storage_object=storage_object,
        storage_generation=storage_generation,
        checksum=checksum,
        status="uploaded",
    )

    session.add(file)

    session.flush()

    return file


def get_file(session, owner_id, file_id):
    file = session.scalar(
        select(UploadedFile).where(
            UploadedFile.id == file_id, UploadedFile.owner_id == owner_id
        )
    )

    if file is None:
        raise LookupError("File not found")

    return file
