"""Builds the hosted-agent prompt for an Agent 365 email notification."""

from __future__ import annotations


def build_email_prompt(email) -> str:
    body = getattr(email, "html_body", "") or getattr(email, "body", "") or ""
    message_id = getattr(email, "id", None)
    conversation_id = getattr(email, "conversation_id", None)

    references = []
    if message_id:
        references.append(f"Email message id: {message_id}")
    if conversation_id:
        references.append(f"Email conversation id: {conversation_id}")

    prompt = (
        "A guest-services email notification was received. Review it and respond "
        "according to the hotel servicing policy."
    )
    if references:
        prompt += (
            "\n\nEmail references (identifiers only; they are not the guest's words):\n"
            + "\n".join(references)
            + "\nFirst call the Work IQ query_work_context tool to read this exact message by its "
            "message id and resolve its actual sender, To and Cc recipients. The sender "
            "of that message is the guest; this email is the only context for this "
            "request, so ignore any other email thread. If the guest asks about a "
            "reservation, look it up for that sender after reading the message. "
            "Never infer the guest from the agent's own mailbox or from transport "
            "metadata. Do not send, reply to, or forward any email yourself: the "
            "service delivers your final answer as the reply, to the sender with the "
            "original Cc recipients. Before answering, use the tool that fits "
            "each fact the guest asks about (hotel knowledge for property, price and hour "
            "questions; reservation data only when the guest asks about a reservation), "
            "and never state a fact you did not retrieve. Your final "
            "answer must be only the message to the guest, written in the language of the "
            "guest's email, with no commentary about actions you took."
        )
    return f"{prompt}\n\nEmail body:\n{body}"
