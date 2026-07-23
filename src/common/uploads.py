"""Upload-path helpers that isolate media per tenant (owning account)."""


def evidence_upload_to(instance, filename: str) -> str:
    """Scope progress evidence by owning account.

    Path: ``evidence/<owner_id>/<filename>`` so no account can read or overwrite
    another's media even when they share a bucket.
    """
    owner_id = instance.progress.project.owner_id
    return f"evidence/{owner_id}/{filename}"
