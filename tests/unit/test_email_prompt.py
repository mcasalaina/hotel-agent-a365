"""Tests for the Agent 365 email notification prompt builder."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[2] / "agent" / "email_prompt.py"
spec = importlib.util.spec_from_file_location("email_prompt", MODULE_PATH)
assert spec is not None and spec.loader is not None
email_prompt = importlib.util.module_from_spec(spec)
sys.modules["email_prompt"] = email_prompt
spec.loader.exec_module(email_prompt)


def test_prompt_includes_references_and_unchanged_body():
    email = SimpleNamespace(id="MSG-1", conversation_id="CONV-1", html_body="<p>Hola</p>")
    prompt = email_prompt.build_email_prompt(email)
    assert "Email message id: MSG-1" in prompt
    assert "Email conversation id: CONV-1" in prompt
    assert prompt.endswith("Email body:\n<p>Hola</p>")
    assert "Cc" in prompt and "Work IQ" in prompt


def test_prompt_falls_back_to_plain_body_without_references():
    email = SimpleNamespace(id=None, conversation_id=None, html_body="", body="Hello")
    prompt = email_prompt.build_email_prompt(email)
    assert "Email message id" not in prompt
    assert prompt.endswith("Email body:\nHello")


def test_prompt_never_names_a_sender_from_metadata():
    email = SimpleNamespace(id="M", conversation_id="C", html_body="x", sender="other@x.com")
    assert "other@x.com" not in email_prompt.build_email_prompt(email)


def test_prompt_forbids_agent_sending_and_requires_grounding():
    email = SimpleNamespace(id="AAA", conversation_id="CCC", html_body="Hola")
    prompt = email_prompt.build_email_prompt(email)
    assert "Do not send, reply to, or forward any email yourself" in prompt
    assert "never state a fact you did not retrieve" in prompt


def test_prompt_names_exact_message_lookup_tool():
    email = SimpleNamespace(id="MSG-1", conversation_id="CONV-1", html_body="x")
    prompt = email_prompt.build_email_prompt(email)
    assert "query_work_context" in prompt
    assert "MSG-1" in prompt
