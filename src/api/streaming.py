import asyncio
import json
from collections.abc import AsyncIterator

from tools.event_stream import WorkflowEvent


def encode_event(event: WorkflowEvent) -> str:
    data = json.dumps(event.data, ensure_ascii=False, allow_nan=False)

    return f"event: {event.event}\ndata: {data}\n\n"


async def stream_events(events: AsyncIterator[WorkflowEvent]) -> AsyncIterator[str]:
    """Keep the connection alive while a provider is processing a step."""
    pending = None

    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(events))

            done, _ = await asyncio.wait({pending}, timeout=10)

            if not done:
                yield ": heartbeat\n\n"
                continue

            try:
                event = pending.result()
            except StopAsyncIteration:
                return

            pending = None
            yield encode_event(event)

    except Exception as error:
        yield encode_event(
            WorkflowEvent(
                event="error",
                data={"message": str(error), "type": type(error).__name__},
            )
        )

    finally:
        if pending is not None:
            pending.cancel()

            await asyncio.gather(pending, return_exceptions=True)

        await events.aclose()
