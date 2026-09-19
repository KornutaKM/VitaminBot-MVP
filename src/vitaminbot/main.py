def healthcheck() -> dict[str, str]:
    """Return the minimal application health payload."""
    return {"status": "ok"}
