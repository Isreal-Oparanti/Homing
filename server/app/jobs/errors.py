class RetryableError(Exception):
    """Temporary failure (timeout, 429, 5xx). The runner retries with backoff."""


class PermanentError(Exception):
    """Bad input or a known dead end. The job is marked failed and not retried.

    The message is shown to the user, so write it in plain language.
    """
