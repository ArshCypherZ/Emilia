import asyncio
import functools
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from multiprocessing import cpu_count

process_pool = ProcessPoolExecutor(max_workers=cpu_count())
thread_pool = ThreadPoolExecutor(max_workers=min(32, cpu_count() + 4))


async def run_in_process(func, *args, **kwargs):
    """
    Runs a blocking function in a separate process.
    Use this for CPU-bound tasks like Image manipulation (PIL), heavy calculations, etc.
    """
    loop = asyncio.get_running_loop()
    # functools.partial is needed to pass kwargs if any,
    # though Executor.submit/run_in_executor usually handles *args.
    # For run_in_executor, we need to partial the function if we have kwargs.
    call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(process_pool, call)


async def run_in_thread(func, *args, **kwargs):
    """
    Runs a blocking function in a separate thread.
    Use this for I/O-bound tasks like file operations, or waiting on subprocesses.
    """
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(thread_pool, call)
