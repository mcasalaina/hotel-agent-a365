LANGUAGE_RESPONSE_GUIDANCE = (
    "Final response requirement: use the user's established conversation language throughout. "
    "The user's latest complete utterance is authoritative: when it is clearly and predominantly "
    "in another language, immediately use that language for the current response and override the "
    "language of earlier turns. An English utterance requires an English response, including "
    "questions about visitors whose names contain accents or come from another language. "
    "Determine the language from the user's complete sentences, not from the visitors' names; "
    "do not infer a visitor's preferred language. "
    "A Spanish utterance requires a Spanish response, and an Arabic utterance requires an Arabic "
    "response. "
    "Do not adopt the language of this tool evidence, and do not switch because of names, accents, "
    "place names, or isolated foreign words."
)


def with_language_response_guidance(evidence: str) -> str:
    return f"{LANGUAGE_RESPONSE_GUIDANCE}\n\nTool evidence:\n{evidence}"
