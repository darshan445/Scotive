"""First-pass is separate from hourly incremental re-eval."""
import inspect

import conversation_first_pass as first_pass
from conversation_first_pass import _has_message_bodies, _has_real_client_email
from incremental_sync import _reevaluate_tracked, reeval_after_user_outbound_send


def test_first_pass_does_not_call_hourly_reeval():
    assert not hasattr(first_pass, "_reevaluate_tracked")
    assert "incremental_sync" not in first_pass.__dict__


def test_decide_requires_bodies_not_client_from():
    src = inspect.getsource(first_pass._decide_from_messages)
    assert "_has_client_reply" not in src
    assert "empty_bodies" in src
    assert "_has_message_bodies" in src


def test_has_message_bodies():
    assert _has_message_bodies([{"body": "  "}, {"body": ""}]) is False
    assert _has_message_bodies([{"body": "I'll pay Friday"}]) is True


def test_invoicing_placeholder_emails():
    assert _has_real_client_email({"counterparty_email": "qbo:1"}) is False
    assert _has_real_client_email({"counterparty_email": "xero:1"}) is False
    assert _has_real_client_email({"counterparty_email": "client@agency.com"}) is True


def test_first_pass_and_sync_now_use_the_same_decide():
    """Onboarding and Sync now: same rulebook, same apply, model fields win."""
    decide = inspect.getsource(first_pass._decide_from_messages)
    reeval = inspect.getsource(_reevaluate_tracked)
    post = inspect.getsource(reeval_after_user_outbound_send)
    for src in (decide, reeval, post):
        assert "extract_reeval_with_rulebook" in src
        assert "apply_rulebook_result" in src
        assert "_write_event" not in src
