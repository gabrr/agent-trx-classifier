from abc import ABC, abstractmethod


class JobService(ABC):
    """Application job operations; callers do not depend on persistence or delivery SDKs."""

    @abstractmethod
    def submit_job(self, owner_id, content, filename, submission_key): ...

    @abstractmethod
    def get_job(self, owner_id, job_id): ...

    @abstractmethod
    def get_result(self, owner_id, job_id): ...

    @abstractmethod
    def retry_job(self, owner_id, job_id, submission_key): ...

    @abstractmethod
    def dispatch_pending_jobs(self, *, owner_id=None, job_id=None, limit=20): ...

    @abstractmethod
    def run_maintenance(self): ...

    @abstractmethod
    async def process_job(self, job_id): ...
