"""Windows event loop helpers used by the uvicorn entrypoint."""

import asyncio
import selectors


def selector_loop_factory(use_subprocess: bool = False) -> asyncio.AbstractEventLoop:
    """
    Create a Selector-based event loop.

    psycopg async cannot run on the Windows default Proactor event loop;
    uvicorn's ``loop`` option accepts a ``module:function`` path pointing
    here so every worker (reload or multiprocess) builds a compatible loop.

    :param use_subprocess: ignored; kept for uvicorn's loop factory protocol.
    :return: a SelectorEventLoop instance.
    """
    return asyncio.SelectorEventLoop(selectors.SelectSelector())
