from datetime import datetime


class RetryableError(Exception):
    """Temporary failure (timeout, 429, 5xx). The runner retries with backoff."""


class PermanentError(Exception):
    """Bad input or a known dead end. The job is marked failed and not retried.

    The message is shown to the user, so write it in plain language.
    """


class DeferredError(Exception):
    """Can't run yet, through no fault of the job (e.g. today's model budget is used up).

    The runner puts the job back until `until` without using up an attempt.
    """

    def __init__(self, message: str, until: datetime):
        super().__init__(message)
        self.until = until
