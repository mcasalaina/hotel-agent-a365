from copy import deepcopy

from run_multilingual_evaluator_quality import _input_provenance_matches, _validation_content


def test_evaluator_input_provenance_requires_exact_cases() -> None:
    expected = [
        {"source_case_id": 16, "evaluation_query": "Question", "evaluation_response": "Answer"},
        {"source_case_id": 17, "evaluation_query": "Next", "evaluation_response": "Next answer"},
    ]
    output = [{"datasource_item": {"item": row}} for row in reversed(expected)]

    assert _input_provenance_matches(output, expected)
    assert _input_provenance_matches([{"datasource_item": row} for row in expected], expected)
    assert not _input_provenance_matches(output[:1], expected)
    assert not _input_provenance_matches([output[0], output[0]], expected)

    changed = deepcopy(output)
    changed[0]["datasource_item"]["item"]["evaluation_response"] = "Different answer"
    assert not _input_provenance_matches(changed, expected)


def test_evaluator_input_provenance_rejects_stale_field_schema() -> None:
    expected = [{"source_case_id": 16, "query": "Question", "response": "Answer"}]
    stale = [
        {
            "datasource_item": {
                "item": {
                    "source_case_id": 16,
                    "evaluation_query": "Question",
                    "evaluation_response": "Answer",
                }
            }
        }
    ]

    assert not _input_provenance_matches(stale, expected)
    assert not _input_provenance_matches([{"datasource_item": None}], expected)


def test_static_language_cases_use_the_verified_canonical_schema() -> None:
    rows = [{"id": 16, "query": "Question", "candidate_response": "Answer"}]

    assert _validation_content(rows) == [
        {"source_case_id": 16, "query": "Question", "response": "Answer"}
    ]
