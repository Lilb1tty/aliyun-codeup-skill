#!/usr/bin/env python3
"""Console entry point; official CLI remains the only API implementation."""
from codeup_secure.cli import main as cli_main

def main():
    import os
    import signal
    result = cli_main()
    if result < 0 and os.name != "nt":
        if -result not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(-result, signal.SIG_DFL)
        os.kill(os.getpid(), -result)
    return result

if __name__ == "__main__":
    raise SystemExit(main())
