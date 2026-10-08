"""Initial TRX schema. Frozen DDL; independent of future ORM changes."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DDL = [
    """CREATE FUNCTION private.valid_probabilities(value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE bucket text; probability numeric; total numeric := 0;
BEGIN
  IF jsonb_typeof(value) <> 'object' OR (SELECT count(*) FROM jsonb_object_keys(value)) <> 4
     OR NOT value ?& ARRAY['installments','fixed','variable','movements'] THEN RETURN false; END IF;
  FOREACH bucket IN ARRAY ARRAY['installments','fixed','variable','movements'] LOOP
    IF jsonb_typeof(value->bucket) <> 'number' THEN RETURN false; END IF;
    probability := (value->>bucket)::numeric;
    IF probability < 0 OR probability > 1 THEN RETURN false; END IF;
    total := total + probability;
  END LOOP;
  RETURN abs(total - 1) <= 0.02;
EXCEPTION WHEN OTHERS THEN RETURN false;
END $$""",
    """CREATE TABLE private.login_attempts (
	id_hash TEXT NOT NULL, 
	browser_binding_hash TEXT NOT NULL, 
	encrypted_pkce_verifier BYTEA NOT NULL, 
	encryption_key_version TEXT NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	consumed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_login_attempts PRIMARY KEY (id_hash)
)""",
    """CREATE INDEX ix_login_attempts_expires_at ON private.login_attempts (expires_at)""",
    """CREATE TABLE private.report_buckets (
	key TEXT NOT NULL, 
	label TEXT NOT NULL, 
	CONSTRAINT pk_report_buckets PRIMARY KEY (key)
)""",
    """CREATE TABLE private.users (
	id UUID NOT NULL, 
	email TEXT, 
	display_name TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id)
)""",
    """CREATE TABLE private.accounts (
	id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	name TEXT NOT NULL, 
	type TEXT NOT NULL, 
	institution_name TEXT, 
	currency TEXT NOT NULL, 
	opening_balance NUMERIC NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_accounts PRIMARY KEY (id), 
	CONSTRAINT uq_accounts_id_owner_id UNIQUE (id, owner_id), 
	CONSTRAINT fk_accounts_owner_id_users FOREIGN KEY(owner_id) REFERENCES private.users (id)
)""",
    """CREATE INDEX ix_accounts_owner_id ON private.accounts (owner_id)""",
    """CREATE TABLE private.activity_events (
	id UUID NOT NULL, 
	changed_by UUID NOT NULL, 
	entity_id UUID NOT NULL, 
	field TEXT NOT NULL, 
	old_value JSONB, 
	new_value JSONB, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_activity_events PRIMARY KEY (id), 
	CONSTRAINT fk_activity_events_changed_by_users FOREIGN KEY(changed_by) REFERENCES private.users (id)
)""",
    """CREATE INDEX ix_activity_events_changed_by ON private.activity_events (changed_by)""",
    """CREATE INDEX ix_activity_events_entity_id ON private.activity_events (entity_id)""",
    """CREATE TABLE private.sessions (
	id_hash TEXT NOT NULL, 
	owner_id UUID NOT NULL, 
	encrypted_provider_tokens BYTEA NOT NULL, 
	encryption_key_version TEXT NOT NULL, 
	csrf_token_hash TEXT NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	refresh_version BIGINT NOT NULL, 
	refresh_claim_expires_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_sessions PRIMARY KEY (id_hash), 
	CONSTRAINT ck_sessions_refresh_version CHECK (refresh_version >= 0), 
	CONSTRAINT fk_sessions_owner_id_users FOREIGN KEY(owner_id) REFERENCES private.users (id)
)""",
    """CREATE INDEX ix_sessions_expires_at ON private.sessions (expires_at)""",
    """CREATE INDEX ix_sessions_owner_id ON private.sessions (owner_id)""",
    """CREATE TABLE private.categories (
	id UUID NOT NULL, 
	owner_id UUID, 
	key TEXT NOT NULL, 
	name TEXT NOT NULL, 
	is_system BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_categories PRIMARY KEY (id), 
	CONSTRAINT ck_categories_category_owner CHECK ((is_system AND owner_id IS NULL) OR (NOT is_system AND owner_id IS NOT NULL)), 
	CONSTRAINT fk_categories_owner_id_users FOREIGN KEY(owner_id) REFERENCES private.users (id)
)""",
    """CREATE INDEX ix_categories_owner_id ON private.categories (owner_id)""",
    """CREATE UNIQUE INDEX uq_system_category_key ON private.categories (key) WHERE is_system""",
    """CREATE UNIQUE INDEX uq_user_category_key ON private.categories (owner_id, key) WHERE NOT is_system""",
    """CREATE TABLE private.uploaded_files (
	id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	filename TEXT NOT NULL, 
	content_type TEXT NOT NULL, 
	size_bytes BIGINT NOT NULL, 
	storage_bucket TEXT NOT NULL, 
	storage_object TEXT NOT NULL, 
	storage_generation TEXT, 
	checksum TEXT, 
	status TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_uploaded_files PRIMARY KEY (id), 
	CONSTRAINT ck_uploaded_files_file_size CHECK (size_bytes >= 0), 
	CONSTRAINT uq_uploaded_files_id_owner_id UNIQUE (id, owner_id), 
	CONSTRAINT fk_uploaded_files_owner_id_users FOREIGN KEY(owner_id) REFERENCES private.users (id)
)""",
    """CREATE INDEX ix_uploaded_files_owner_id ON private.uploaded_files (owner_id)""",
    """CREATE TABLE private.batches (
	id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_batches PRIMARY KEY (id), 
	CONSTRAINT uq_batches_id_owner_id UNIQUE (id, owner_id), 
	CONSTRAINT fk_batches_owner_id_users FOREIGN KEY(owner_id) REFERENCES private.users (id)
)""",
    """CREATE INDEX ix_batches_owner_id ON private.batches (owner_id)""",
    """CREATE TABLE private.jobs (
	id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	batch_id UUID, 
	uploaded_file_id UUID NOT NULL, 
	retry_of_job_id UUID, 
	submission_key TEXT NOT NULL, 
	status TEXT NOT NULL, 
	current_stage TEXT, 
	active_attempt_id UUID, 
	claim_expires_at TIMESTAMP WITH TIME ZONE, 
	deadline_at TIMESTAMP WITH TIME ZONE, 
	result JSONB, 
	result_schema_version TEXT, 
	success_message TEXT, 
	error_code TEXT, 
	error_reason TEXT, 
	diagnostic_reference TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_jobs PRIMARY KEY (id), 
	CONSTRAINT uq_jobs_owner_id_submission_key UNIQUE (owner_id, submission_key), 
	CONSTRAINT ck_jobs_job_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed')), 
	CONSTRAINT uq_jobs_id_owner_id UNIQUE (id, owner_id), 
	CONSTRAINT fk_jobs_batch_id_batches FOREIGN KEY(batch_id, owner_id) REFERENCES private.batches (id, owner_id), 
	CONSTRAINT fk_jobs_uploaded_file_id_uploaded_files FOREIGN KEY(uploaded_file_id, owner_id) REFERENCES private.uploaded_files (id, owner_id), 
	CONSTRAINT fk_jobs_retry_of_job_id_jobs FOREIGN KEY(retry_of_job_id, owner_id) REFERENCES private.jobs (id, owner_id), 
	CONSTRAINT fk_jobs_owner_id_users FOREIGN KEY(owner_id) REFERENCES private.users (id)
)""",
    """CREATE INDEX ix_jobs_batch_id ON private.jobs (batch_id)""",
    """CREATE INDEX ix_jobs_owner_id ON private.jobs (owner_id)""",
    """CREATE INDEX ix_jobs_owner_status_created ON private.jobs (owner_id, status, created_at)""",
    """CREATE INDEX ix_jobs_retry_of_job_id ON private.jobs (retry_of_job_id)""",
    """CREATE INDEX ix_jobs_uploaded_file_id ON private.jobs (uploaded_file_id)""",
    """CREATE TABLE private.job_attempts (
	id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	attempt_number INTEGER NOT NULL, 
	status TEXT NOT NULL, 
	claim_expires_at TIMESTAMP WITH TIME ZONE, 
	started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	error_code TEXT, 
	error_details JSONB, 
	CONSTRAINT pk_job_attempts PRIMARY KEY (id), 
	CONSTRAINT uq_job_attempts_id_job_id UNIQUE (id, job_id), 
	CONSTRAINT uq_job_attempts_job_id_attempt_number UNIQUE (job_id, attempt_number), 
	CONSTRAINT ck_job_attempts_attempt_number CHECK (attempt_number > 0), 
	CONSTRAINT ck_job_attempts_attempt_status CHECK (status IN ('running', 'succeeded', 'failed')), 
	CONSTRAINT fk_job_attempts_job_id_jobs FOREIGN KEY(job_id) REFERENCES private.jobs (id)
)""",
    """CREATE INDEX ix_job_attempts_job_id ON private.job_attempts (job_id)""",
    """CREATE TABLE private.run_metrics (
	job_id UUID NOT NULL, 
	elapsed_seconds DOUBLE PRECISION NOT NULL, 
	classification_seconds DOUBLE PRECISION NOT NULL, 
	classification_model_calls INTEGER NOT NULL, 
	transaction_count INTEGER NOT NULL, 
	CONSTRAINT pk_run_metrics PRIMARY KEY (job_id), 
	CONSTRAINT fk_run_metrics_job_id_jobs FOREIGN KEY(job_id) REFERENCES private.jobs (id)
)""",
    """CREATE INDEX ix_run_metrics_job_id ON private.run_metrics (job_id)""",
    """CREATE TABLE private.outbox (
	id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	action TEXT NOT NULL, 
	task_name TEXT NOT NULL, 
	payload JSONB NOT NULL, 
	dispatch_status TEXT NOT NULL, 
	retry_count INTEGER NOT NULL, 
	next_attempt_at TIMESTAMP WITH TIME ZONE, 
	dispatched_at TIMESTAMP WITH TIME ZONE, 
	last_error TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_outbox PRIMARY KEY (id), 
	CONSTRAINT uq_outbox_task_name UNIQUE (task_name), 
	CONSTRAINT ck_outbox_outbox_retry_count CHECK (retry_count >= 0), 
	CONSTRAINT fk_outbox_job_id_jobs FOREIGN KEY(job_id) REFERENCES private.jobs (id)
)""",
    """CREATE INDEX ix_outbox_dispatch_retry ON private.outbox (dispatch_status, next_attempt_at)""",
    """CREATE INDEX ix_outbox_job_id ON private.outbox (job_id)""",
    """CREATE TABLE private.statements (
	id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	account_id UUID, 
	kind TEXT NOT NULL, 
	institution_name TEXT, 
	currency TEXT, 
	statement_due_date DATE, 
	statement_close_date DATE, 
	statement_total TEXT, 
	page_count INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_statements PRIMARY KEY (id), 
	CONSTRAINT uq_statements_job_id UNIQUE (job_id), 
	CONSTRAINT ck_statements_statement_kind CHECK (kind IN ('credit_card', 'checking_account', 'unknown')), 
	CONSTRAINT uq_statements_id_owner_id UNIQUE (id, owner_id), 
	CONSTRAINT fk_statements_job_id_jobs FOREIGN KEY(job_id, owner_id) REFERENCES private.jobs (id, owner_id), 
	CONSTRAINT fk_statements_account_id_accounts FOREIGN KEY(account_id, owner_id) REFERENCES private.accounts (id, owner_id), 
	CONSTRAINT fk_statements_owner_id_users FOREIGN KEY(owner_id) REFERENCES private.users (id)
)""",
    """CREATE INDEX ix_statements_account_id ON private.statements (account_id)""",
    """CREATE INDEX ix_statements_job_id ON private.statements (job_id)""",
    """CREATE INDEX ix_statements_owner_id ON private.statements (owner_id)""",
    """CREATE TABLE private.checkpoints (
	id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	attempt_id UUID NOT NULL, 
	stage TEXT NOT NULL, 
	output JSONB, 
	storage_reference TEXT, 
	input_fingerprint TEXT NOT NULL, 
	workflow_version TEXT NOT NULL, 
	model_version TEXT NOT NULL, 
	schema_version TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_checkpoints PRIMARY KEY (id), 
	CONSTRAINT ck_checkpoints_checkpoint_output CHECK (output IS NOT NULL OR storage_reference IS NOT NULL), 
	CONSTRAINT fk_checkpoints_attempt_id_job_attempts FOREIGN KEY(attempt_id, job_id) REFERENCES private.job_attempts (id, job_id), 
	CONSTRAINT fk_checkpoints_job_id_jobs FOREIGN KEY(job_id) REFERENCES private.jobs (id)
)""",
    """CREATE INDEX ix_checkpoints_attempt_id ON private.checkpoints (attempt_id)""",
    """CREATE INDEX ix_checkpoints_job_id ON private.checkpoints (job_id)""",
    """CREATE TABLE private.events (
	id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	sequence BIGINT NOT NULL, 
	attempt_id UUID, 
	event_type TEXT NOT NULL, 
	data JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_events PRIMARY KEY (id), 
	CONSTRAINT uq_events_job_id_sequence UNIQUE (job_id, sequence), 
	CONSTRAINT ck_events_event_sequence CHECK (sequence > 0), 
	CONSTRAINT fk_events_attempt_id_job_attempts FOREIGN KEY(attempt_id, job_id) REFERENCES private.job_attempts (id, job_id), 
	CONSTRAINT fk_events_job_id_jobs FOREIGN KEY(job_id) REFERENCES private.jobs (id)
)""",
    """CREATE INDEX ix_events_attempt_id ON private.events (attempt_id)""",
    """CREATE INDEX ix_events_job_id ON private.events (job_id)""",
    """CREATE TABLE private.transactions (
	id UUID NOT NULL, 
	trx_id TEXT NOT NULL, 
	statement_id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	position INTEGER NOT NULL, 
	category_id UUID, 
	date DATE, 
	description TEXT, 
	amount TEXT, 
	currency TEXT, 
	cardholder TEXT, 
	card_last4 TEXT, 
	payment_method TEXT, 
	merchant_name TEXT, 
	installments_current INTEGER, 
	installments INTEGER, 
	foreign_amount TEXT, 
	foreign_currency TEXT, 
	running_balance TEXT, 
	report_bucket TEXT NOT NULL, 
	classification_confidence DOUBLE PRECISION NOT NULL, 
	classification_probabilities JSONB NOT NULL, 
	report_bucket_override TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_transactions PRIMARY KEY (id), 
	CONSTRAINT uq_transactions_statement_id_trx_id UNIQUE (statement_id, trx_id), 
	CONSTRAINT uq_transactions_statement_id_position UNIQUE (statement_id, position), 
	CONSTRAINT ck_transactions_transaction_position CHECK (position >= 0), 
	CONSTRAINT ck_transactions_confidence_range CHECK (classification_confidence >= 0 AND classification_confidence <= 1), 
	CONSTRAINT ck_transactions_probabilities CHECK (private.valid_probabilities(classification_probabilities)), 
	CONSTRAINT uq_transactions_id_owner_id UNIQUE (id, owner_id), 
	CONSTRAINT fk_transactions_statement_id_statements FOREIGN KEY(statement_id, owner_id) REFERENCES private.statements (id, owner_id), 
	CONSTRAINT fk_transactions_owner_id_users FOREIGN KEY(owner_id) REFERENCES private.users (id), 
	CONSTRAINT fk_transactions_category_id_categories FOREIGN KEY(category_id) REFERENCES private.categories (id), 
	CONSTRAINT fk_transactions_report_bucket_report_buckets FOREIGN KEY(report_bucket) REFERENCES private.report_buckets (key), 
	CONSTRAINT fk_transactions_report_bucket_override_report_buckets FOREIGN KEY(report_bucket_override) REFERENCES private.report_buckets (key)
)""",
    """CREATE INDEX ix_transactions_category_id ON private.transactions (category_id)""",
    """CREATE INDEX ix_transactions_owner_id ON private.transactions (owner_id)""",
    """CREATE INDEX ix_transactions_statement_id ON private.transactions (statement_id)""",
    """ALTER TABLE private.jobs ADD CONSTRAINT fk_active_attempt_job FOREIGN KEY(active_attempt_id, id) REFERENCES private.job_attempts (id, job_id)""",
    """INSERT INTO private.report_buckets (key, label) VALUES ('installments','Installments'), ('fixed','Fixed'), ('variable','Variable'), ('movements','Movements')""",
    """CREATE FUNCTION private.check_category_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.category_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM private.categories WHERE id = NEW.category_id
      AND (is_system OR owner_id = NEW.owner_id)
  ) THEN RAISE EXCEPTION 'Category does not belong to transaction owner'; END IF;
  RETURN NEW;
END $$""",
    """CREATE TRIGGER transaction_category_owner BEFORE INSERT OR UPDATE OF category_id, owner_id
ON private.transactions FOR EACH ROW EXECUTE FUNCTION private.check_category_owner()""",
    """CREATE FUNCTION private.protect_category_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.owner_id IS DISTINCT FROM OLD.owner_id OR NEW.is_system IS DISTINCT FROM OLD.is_system THEN
     RAISE EXCEPTION 'Category ownership is immutable';
  END IF;
  RETURN NEW;
END $$""",
    """CREATE TRIGGER protect_category_owner BEFORE UPDATE OF owner_id, is_system
ON private.categories FOR EACH ROW EXECUTE FUNCTION private.protect_category_owner()""",
    """DO $$ BEGIN
 IF current_setting('trx.auth_same_project', true) = 'true' THEN
   IF to_regclass('auth.users') IS NULL THEN RAISE EXCEPTION 'Same-project Auth users table missing'; END IF;
   ALTER TABLE private.users ADD CONSTRAINT fk_verified_auth_user FOREIGN KEY (id) REFERENCES auth.users(id);
 END IF;
END $$""",
    """REVOKE ALL ON SCHEMA private FROM PUBLIC""",
    """GRANT USAGE ON SCHEMA private TO trx_app""",
    """GRANT SELECT ON ALL TABLES IN SCHEMA private TO trx_app""",
    """REVOKE ALL ON private.alembic_version FROM trx_app""",
    """GRANT INSERT, UPDATE ON private.accounts TO trx_app""",
    """GRANT INSERT, UPDATE ON private.sessions TO trx_app""",
    """GRANT INSERT, UPDATE ON private.login_attempts TO trx_app""",
    """GRANT INSERT, UPDATE ON private.categories TO trx_app""",
    """GRANT INSERT ON private.checkpoints TO trx_app""",
    """GRANT INSERT ON private.events TO trx_app""",
    """GRANT INSERT, UPDATE ON private.uploaded_files TO trx_app""",
    """GRANT INSERT, UPDATE ON private.batches TO trx_app""",
    """GRANT INSERT, UPDATE ON private.jobs TO trx_app""",
    """GRANT INSERT, UPDATE ON private.job_attempts TO trx_app""",
    """GRANT INSERT ON private.run_metrics TO trx_app""",
    """GRANT INSERT, UPDATE ON private.outbox TO trx_app""",
    """GRANT INSERT ON private.statements TO trx_app""",
    """GRANT INSERT, UPDATE ON private.transactions TO trx_app""",
    """GRANT INSERT, UPDATE ON private.users TO trx_app""",
    """GRANT INSERT ON private.activity_events TO trx_app""",
    """REVOKE UPDATE, DELETE, TRUNCATE ON private.activity_events FROM trx_app""",
]


def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    # Retention policy is not defined; never erase result or audit history.
    raise RuntimeError(
        "Destructive downgrade is unsupported; restore an administrative backup"
    )
