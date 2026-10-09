from threading import Event, get_ident
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest

from api.jobs import stream_job_events


@pytest.mark.parametrize("cancel_stream", [False, True])
def test_cleanup_does_not_block_event_loop_and_survives_disconnect(cancel_stream):
    subscribed = Event()

    cleanup_started = Event()

    release_cleanup = Event()

    removed = []
    cleanup_threads = []

    class Listener:
        def subscribe(self, *args, **kwargs):
            subscribed.set()

            return "subscription"

        def unsubscribe(self, token):
            cleanup_threads.append(get_ident())

            cleanup_started.set()

            if not release_cleanup.wait(timeout=3):
                raise TimeoutError("Cleanup was not released by the event loop")

            removed.append(token)

    async def disconnected():
        if cancel_stream:
            await anyio.sleep_forever()

        return True

    async def wait_for(signal):
        with anyio.fail_after(1):
            while not signal.is_set():
                await anyio.sleep(0.001)

    async def run():
        event_loop_thread = get_ident()

        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(job_listener=Listener())),
            is_disconnected=disconnected,
        )

        response = await stream_job_events(
            request,
            uuid4(),
            SimpleNamespace(id=uuid4()),
            SimpleNamespace(get_job=lambda *args: {"status": "running"}),
            SimpleNamespace(is_token_active=lambda _: True),
            after_sequence=0,
        )

        async def consume(*, task_status=anyio.TASK_STATUS_IGNORED):
            with anyio.CancelScope() as scope:
                task_status.started(scope)

                async for _ in response.body_iterator:
                    pass

        try:
            async with anyio.create_task_group() as tasks:
                scope = await tasks.start(consume)

                await wait_for(subscribed)

                if cancel_stream:
                    scope.cancel()

                await wait_for(cleanup_started)

                # The event loop keeps running while synchronous cleanup waits.
                assert len(cleanup_threads) == 1
                assert cleanup_threads[0] != event_loop_thread
                assert removed == []
                release_cleanup.set()

        finally:
            release_cleanup.set()

        assert removed == ["subscription"]

    anyio.run(run)
