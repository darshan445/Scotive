"""Compatibility wrappers for conversation first-pass.

Implementation: conversation_first_pass (match + decide from those messages).
Hourly windowed re-eval: incremental_sync._reevaluate_tracked — do not call it here.
"""
from conversation_first_pass import (  # noqa: F401
    _has_real_client_email,
    _item_snapshot,
    _pick_best_thread,
    enqueue_conversation_first_pass as enqueue_qbo_conversation_match,
    get_conversation_job_status as get_qbo_pipeline_status,
)
from invoice_mail_match import waterfall_threads  # noqa: F401
