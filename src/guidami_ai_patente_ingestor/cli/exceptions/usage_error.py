class UsageError(Exception):
    """A command-line usage problem detected after argument parsing.

    `main` reports it through `parser.error`, so the user sees the usual usage message
    and exit code 2, exactly like an argparse-level error.
    """
