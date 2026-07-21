from __future__ import annotations


def _enable_tracing_if_available() -> None:
    """Enable ASSERT/OpenInference auto-tracing when the optional tracing extra is installed.

    ``assert-ai`` is NOT a runtime dependency of this agent (see requirements.txt /
    pyproject.toml ``[project.optional-dependencies] tracing``). In a normal production
    install the import below raises ``ImportError`` and this function is a no-op, so the
    agent starts unchanged. When the agent is installed with ``pip install .[tracing]``,
    ``auto_trace.enable()`` installs OpenInference instrumentors and only exports spans
    when a Phoenix/OTLP collector is actually configured — so it stays safe in prod.
    """
    try:
        from assert_ai import auto_trace
    except ImportError:
        return
    try:
        auto_trace.enable()
    except Exception:
        # Tracing must never break agent startup; any tracing failure is a no-op.
        return


def main() -> None:
    # Install instrumentation before the runtime (and the MAF agent/clients) is imported
    # or constructed, so spans capture the agent's model and tool calls.
    _enable_tracing_if_available()

    from hotel_servicing_agent.runtime import main as _runtime_main

    _runtime_main()


if __name__ == "__main__":
    main()
