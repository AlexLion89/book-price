"""Everything that differs between Windows and macOS; the rest of the program is shared and does not look at the OS.

Both modules offer the same names: NAME, LABEL, OUTBOX_WHERE, WINDOW_ARGS, SEARCH_ARGS, REUSE_ADDRESS, data_root,
outbox, message, reveal, first_run, browser_paths, launch_window, processes, profile_in_use, Process, ssl_context.
"""
import sys

if sys.platform == "darwin":
    from . import mac as current
else:
    from . import windows as current
