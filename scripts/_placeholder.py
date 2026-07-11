from __future__ import annotations


def unavailable(workstream: str) -> int:
    print(
        f"{workstream} is reserved by the approved plan and is not implemented "
        "in the repository bootstrap."
    )
    return 2
