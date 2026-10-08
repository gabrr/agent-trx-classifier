# Google Cloud Storage

Stores private source PDFs. PostgreSQL stores the object reference, not PDF bytes.
Setup: **CLI**, after the [bootstrap](README.md).

## Create the bucket

```sh
gcloud storage buckets create "gs://$TRX_BUCKET" --location="$TRX_REGION" --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention

gcloud storage buckets add-iam-policy-binding "gs://$TRX_BUCKET" --member="serviceAccount:$TRX_RUNTIME_SA" --role=roles/storage.objectUser

gcloud storage buckets describe "gs://$TRX_BUCKET"
```

The runtime uploads, downloads, and cleans up objects using its service identity.
No downloaded Google service-account key is needed. Set `PDF_BUCKET` in Cloud Run.

## Application integration

Accept one multipart batch totaling at most **30,000,000 file bytes**. Validate
files independently, save accepted PDFs using unique job-based object names, then
persist/enqueue their jobs through the transactional outbox. Retain private large
conversion checkpoints when needed for saved-stage recovery; PostgreSQL stores
the reference/version. User retries can reuse their owned PDF and compatible
checkpoints without uploading again. Stream transfers instead of retaining the whole batch
in memory. Clean up abandoned uploads and reconcile partial failures.

Keep Cloud Run and the bucket in the same region. Downloads to browsers require
ownership checks; use the backend or short-lived signed URLs if later needed.
Direct browser uploads and bucket CORS are not required for the agreed API upload.

## Retention and verification

Keep accepted source PDFs after successful extraction, as decided. They allow
verification against the original statement and reprocessing when extraction or
classification changes. PostgreSQL remains the readable source for extracted
information/results; it holds each PDF's private object reference.

Do not add automatic lifecycle deletion yet. The earlier 30-day example was a
cost assumption, not an agreed policy. Final retention/user deletion rules still
need definition. Clean up abandoned uploads separately from retained job PDFs;
never delete objects still needed by active attempts. Include soft-deleted objects
and object versions in the storage budget.

Exact duplicate detection is deferred. Identical PDFs may create separate jobs
for now. If added later, compare content hashes within the user's authorized scope;
never reveal another user's upload or reuse its result without permission.

Verify that anonymous reads fail and that the runtime can save/read a PDF.
Confirm oversized batches are rejected before creating processing jobs.

[Bucket creation](https://cloud.google.com/storage/docs/creating-buckets)
· [Storage pricing](https://cloud.google.com/storage/pricing)
