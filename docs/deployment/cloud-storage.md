# Cloud Storage

Cloud Storage holds private PDF and CSV inputs. PostgreSQL holds each file's bucket, object name, generation and checksum. Complete the [bootstrap](README.md#google-cloud-bootstrap) first.

## Create the bucket

```sh
gcloud storage buckets create "gs://$GCS_BUCKET" --location="$TASKS_LOCATION" \
  --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention

gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET" \
  --member="serviceAccount:$RUNTIME_EMAIL" --role=roles/storage.objectUser

gcloud storage buckets describe "gs://$GCS_BUCKET"
```

The runtime uses its service identity for upload, read and cleanup. Set `GCS_BUCKET` in Cloud Run. Keep the bucket and backend in the same region.

## File ownership and retention

Uploads pass through FastAPI's authenticated [job API](../trx-classifier-contract.md#http-api). Object names include the owner, a unique upload identifier and a checksum. The application reads and deletes the persisted generation rather than whichever version happens to exist later.

Source files remain after processing, allowing reprocessing and comparison with the original. User retry reuses the retained file. Repeated submissions with the same key are reconciled; content hashes alone do not reject duplicate uploads.

A file upload precedes the database transaction. If the commit outcome is unknown, the service keeps the object because it may belong to a committed job. Cleanup of abandoned uploads must reconcile database references first. See [submission flow](../trx-system-design/01-architecture-and-services.md#submission-and-processing).

Automatic lifecycle deletion and user deletion are not configured. Define retention and reconciliation before enabling deletion. Account for soft-deleted objects and versions in storage estimates. The API currently exposes no file-download route.

## Verify

Confirm anonymous reads fail, the runtime can upload/read the persisted generation, and an invalid or oversized input is rejected before upload. Verify that cleanup cannot delete another generation or an active job's input.

Implementation: [storage adapter](../../src/tools/object_storage/google.py). [Bucket creation](https://cloud.google.com/storage/docs/creating-buckets), [pricing](https://cloud.google.com/storage/pricing).
