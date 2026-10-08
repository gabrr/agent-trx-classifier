import logging
import threading
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
from sqlalchemy.engine import make_url

from .repositories.events import replay

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    owner_id: UUID
    job_id: UUID
    sequence: int
    callback: object


class JobUpdateListener:
    """Session-capable LISTEN connection, durable replay, no progress polling.

    Callbacks run on a database thread. Async consumers must bridge via
    loop.call_soon_threadsafe. A failed callback leaves its cursor unchanged.
    """

    def __init__(self, url, factory):
        self.url = (
            make_url(url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )

        self.factory = factory
        self._stop = threading.Event()

        self._lock = threading.RLock()

        self._subscriptions = {}
        self._thread = None
        self.connected = threading.Event()

    def start(self):
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="trx-job-listener"
        )

        self._thread.start()

    def close(self):
        self._stop.set()

        if self._thread:
            self._thread.join(timeout=5)

    def subscribe(self, owner_id, job_id, callback, *, after_sequence=0):
        token = uuid4()

        # Register before replay; this lock serializes delivery and deduplication.
        with self._lock:
            self._subscriptions[token] = Subscription(
                owner_id, job_id, after_sequence, callback
            )

            try:
                self._catch_up(job_id)

            except Exception:
                del self._subscriptions[token]
                raise

        return token

    def unsubscribe(self, token):
        with self._lock:
            self._subscriptions.pop(token, None)

    def _catch_up(self, job_id=None):
        with self._lock:
            for subscriber in list(self._subscriptions.values()):
                if job_id is not None and subscriber.job_id != job_id:
                    continue

                with self.factory() as session:
                    events = replay(
                        session,
                        subscriber.owner_id,
                        subscriber.job_id,
                        after_sequence=subscriber.sequence,
                    )

                for event in events:
                    subscriber.callback(event)

                    subscriber.sequence = event.sequence

    def _run(self):
        delay = 1
        while not self._stop.is_set():
            try:
                with psycopg.connect(
                    self.url,
                    autocommit=True,
                    connect_timeout=3,
                    application_name="trx-job-listener",
                ) as connection:
                    connection.execute("LISTEN job_updates")

                    # LISTEN is active before replay, including after reconnect.
                    self._catch_up()

                    self.connected.set()

                    delay = 1
                    while not self._stop.is_set():
                        for notification in connection.notifies(
                            timeout=1, stop_after=1
                        ):
                            try:
                                job_id = UUID(notification.payload)

                            except ValueError:
                                continue

                            self._catch_up(job_id)

            except Exception:
                # Never log exception strings: connection errors can contain secrets.
                logger.warning("Job listener disconnected; reconnecting")

            finally:
                self.connected.clear()

            self._stop.wait(delay)

            delay = min(delay * 2, 30)
