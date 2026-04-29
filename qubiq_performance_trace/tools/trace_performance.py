# Copyright 2026 QUBIQ (https://www.qubiq.es)
# License OPL-1.0

import functools
import itertools
import sys
import time

from .trace_server import push_trace_event, start_trace_server

_CALL_COUNTER = itertools.count(1)


def trace_performance(
    method=None, module_filter="/custom/src/", exclude_filter=None, min_time=0.0
):
    """Trace recursive Python calls executed inside the decorated method.

    This decorator uses ``sys.setprofile`` to inspect function calls triggered during
    the execution of the decorated method. It measures elapsed time for each matched
    call and sends trace events to the local performance trace server.

    Args:
        method (Callable, optional): Decorated function when the decorator is used
            without parentheses, for example ``@trace_performance``.
        module_filter (str | list | tuple | set | None): Include filter based on the
            Python file path. If ``None`` or empty, every module is traced. If a
            string is provided, only files containing that string are traced. If a
            list, tuple or set is provided, files matching any entry are traced.
        exclude_filter (str | list | tuple | set | None): Exclude filter based on
            the Python file path. Matching files are ignored even if they match
            ``module_filter``.
        min_time (float): Minimum execution time, in seconds, required for a call to
            be sent to the trace server. Calls faster than this value are ignored.

    Returns:
        Callable: The wrapped method with performance tracing enabled.

    Example:
        .. code-block:: python

            @trace_performance(
                module_filter=[
                    "/opt/odoo/auto/addons/hr_holidays/",
                    "/opt/odoo/auto/addons/mtech_extra_time/",
                ],
                exclude_filter="/opt/odoo/custom/src/odoo/odoo/",
                min_time=0.05,
            )
            def action_approve(self):
                ...
    """

    def decorator(func):
        """Build the actual decorator for the target function.

        Args:
            func (Callable): Function or method that will be wrapped with
                performance tracing.

        Returns:
            Callable: Wrapped function that enables profiling only during the
            execution of ``func``.
        """

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            """Execute the decorated method with temporary profiling enabled.

            The wrapper starts the local trace server, prepares the call stack metadata,
            installs the profiling callback with ``sys.setprofile`` and restores the
            previous profiler when the decorated method finishes.

            Args:
                self (odoo.models.Model): Current Odoo recordset.
                *args: Positional arguments forwarded to the decorated method.
                **kwargs: Keyword arguments forwarded to the decorated method.

            Returns:
                Any: Return value of the decorated method.
            """
            start_trace_server()

            frame_stack = []
            frame_data = {}

            def send(event):
                """Add a timestamp to a trace event and publish it to the trace server.

                Args:
                    event (dict): Trace event data to be sent. The dictionary is mutated by
                        adding a ``timestamp`` key before being pushed to the shared trace
                        queue/history.
                """
                event["timestamp"] = time.time()
                push_trace_event(event)

            def match_filter(filename):
                """Return whether a Python file should be included in the trace.

                The exclude filter has priority over the include filter. If ``filename``
                matches ``exclude_filter``, the function returns ``False``
                even if it also matches ``module_filter``.

                Args:
                    filename (str): Absolute path of the Python file being profiled.

                Returns:
                    bool: ``True`` if the file should be traced, ``False`` otherwise.
                """
                if exclude_filter:
                    if isinstance(exclude_filter, (list, tuple, set)):
                        if any(path in filename for path in exclude_filter):
                            return False
                    elif exclude_filter in filename:
                        return False

                if not module_filter:
                    return True

                if isinstance(module_filter, (list, tuple, set)):
                    if len(module_filter) == 0:
                        return True
                    return any(path in filename for path in module_filter)

                return module_filter in filename

            root_call_id = f"root-{next(_CALL_COUNTER)}"
            root_function = (
                f"{getattr(self, '_name', self.__class__.__name__)}.{func.__name__}"
            )
            root_start = time.perf_counter()

            send(
                {
                    "event_type": "root_start",
                    "call_id": root_call_id,
                    "parent_id": None,
                    "filename": "",
                    "function": root_function,
                    "depth": 0,
                    "elapsed": 0,
                    "message": "START",
                }
            )

            def profiler(frame, event, arg):
                """Handle low-level profiling events emitted by ``sys.setprofile``.

                This callback receives Python call, return and exception events while the
                decorated method is running. It stores call metadata on entry, calculates
                elapsed time on return, and sends structured trace events only when the call
                matches the configured filters and exceeds ``min_time``.

                Args:
                    frame (types.FrameType): Current execution frame.
                    event (str): Profiling event name. Expected values are ``"call"``,
                        ``"return"`` and ``"exception"``.
                    arg (Any): Event-specific payload. For exception events, this contains
                        ``(exc_type, exc_value, traceback)``.
                """
                if event not in ("call", "return", "exception"):
                    return

                filename = frame.f_code.co_filename

                if not match_filter(filename):
                    return

                frame_id = id(frame)

                if event == "call":
                    parent_frame_id = frame_stack[-1] if frame_stack else None
                    call_id = f"call-{next(_CALL_COUNTER)}"

                    frame_stack.append(frame_id)
                    frame_data[frame_id] = {
                        "call_id": call_id,
                        "parent_frame_id": parent_frame_id,
                        "filename": filename,
                        "function": frame.f_code.co_name,
                        "start": time.perf_counter(),
                        "depth": len(frame_stack),
                    }

                elif event == "return":
                    data = frame_data.pop(frame_id, None)

                    if not data:
                        return

                    elapsed = time.perf_counter() - data["start"]

                    if frame_stack and frame_stack[-1] == frame_id:
                        frame_stack.pop()
                    elif frame_id in frame_stack:
                        frame_stack.remove(frame_id)
                    if elapsed < min_time:
                        return

                    parent_id = root_call_id
                    parent_frame_id = data["parent_frame_id"]

                    if parent_frame_id and parent_frame_id in frame_data:
                        parent_id = frame_data[parent_frame_id]["call_id"]

                    base_event = {
                        "call_id": data["call_id"],
                        "parent_id": parent_id,
                        "filename": data["filename"],
                        "function": data["function"],
                        "depth": data["depth"],
                    }

                    send(
                        {
                            **base_event,
                            "event_type": "start",
                            "elapsed": 0,
                            "message": "START",
                        }
                    )

                    send(
                        {
                            **base_event,
                            "event_type": "end",
                            "elapsed": elapsed,
                            "message": "END",
                        }
                    )

                elif event == "exception":
                    data = frame_data.get(frame_id)
                    exc_type, exc_value, _traceback = arg

                    send(
                        {
                            "event_type": "error",
                            "call_id": data["call_id"]
                            if data
                            else f"error-{next(_CALL_COUNTER)}",
                            "parent_id": root_call_id,
                            "filename": filename,
                            "function": frame.f_code.co_name,
                            "depth": data["depth"] if data else len(frame_stack),
                            "elapsed": 0,
                            "message": f"{exc_type.__name__}: {exc_value}",
                        }
                    )

            previous_profiler = sys.getprofile()
            sys.setprofile(profiler)

            try:
                return func(self, *args, **kwargs)
            finally:
                sys.setprofile(previous_profiler)

                elapsed = time.perf_counter() - root_start

                send(
                    {
                        "event_type": "root_end",
                        "call_id": root_call_id,
                        "parent_id": None,
                        "filename": "",
                        "function": root_function,
                        "depth": 0,
                        "elapsed": elapsed,
                        "message": "END",
                    }
                )

        return wrapper

    if method is not None:
        # Support usage without parentheses: @trace_performance
        return decorator(method)

    # Support usage with parameters: @trace_performance(min_time=0.05)
    return decorator
