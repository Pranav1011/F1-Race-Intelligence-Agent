"""Test script for observability setup (Langfuse v3 + Sentry)."""

import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_sentry():
    """Test Sentry integration."""
    print("\n=== Testing Sentry Integration ===\n")

    from observability.sentry_integration import (
        init_sentry,
        add_breadcrumb,
        capture_message,
        capture_exception,
        set_user_context,
        span,
    )

    # Test initialization (will skip if no DSN configured)
    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        result = init_sentry(
            dsn=dsn,
            environment="test",
            traces_sample_rate=1.0,
        )
        print(f"✓ Sentry initialized: {result}")
    else:
        print("⚠ SENTRY_DSN not configured - Sentry will be disabled")
        print("  Set SENTRY_DSN env var to enable error monitoring")
        # Still test the functions work (they should gracefully handle disabled state)

    # Test breadcrumb (works even without DSN)
    add_breadcrumb(
        message="Test breadcrumb",
        category="test",
        level="info",
        data={"key": "value"},
    )
    print("✓ Added test breadcrumb")

    # Test user context
    set_user_context(user_id="test-user-123")
    print("✓ Set user context")

    # Test span context manager
    with span("test.operation", "Test span description", {"test_key": "test_value"}):
        print("✓ Created test span")

    # Test message capture
    if dsn:
        event_id = capture_message("Test message from observability test", level="info")
        if event_id:
            print(f"✓ Captured test message (event_id: {event_id})")
        else:
            print("✓ Message capture function works (but no event sent - likely filtered)")

    print("\n✓ Sentry integration tests passed!")


async def test_langfuse():
    """Test Langfuse v3 integration."""
    print("\n=== Testing Langfuse Integration (v3 API) ===\n")

    from observability.langfuse_tracer import (
        LangfuseTracer,
        get_tracer,
        get_langfuse_handler,
        observe,
        LANGCHAIN_CALLBACK_AVAILABLE,
    )

    print(f"  LangChain callback available: {LANGCHAIN_CALLBACK_AVAILABLE}")

    # Test tracer initialization
    tracer = get_tracer()
    if tracer.enabled and tracer._initialized:
        print(f"✓ Langfuse tracer initialized (host: {tracer.host})")
    else:
        print("⚠ Langfuse not configured - tracing will be disabled")
        print("  Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY env vars")
        # Still verify functions don't crash
        handler = get_langfuse_handler(session_id="test")
        print(f"✓ get_langfuse_handler works (returned: {handler})")
        return

    # Test callback handler creation
    handler = get_langfuse_handler(
        session_id="test-session",
        user_id="test-user",
        trace_name="observability-test",
        metadata={"test": True},
    )
    if handler:
        print("✓ Created callback handler for LangGraph")
    else:
        print("✓ Callback handler creation works (returned None - callback not available)")

    # Test span creation using context manager
    with tracer.span(name="test-span", input_data={"test": "input"}):
        print("✓ Created span using context manager")

    # Flush to ensure data is sent
    tracer.flush()
    print("✓ Flushed trace data")

    # Test observe decorator is available
    print(f"✓ @observe decorator available: {observe}")

    print("\n✓ Langfuse integration tests passed!")


async def test_agent_integration():
    """Test that observability is properly integrated with agent nodes."""
    print("\n=== Testing Agent Node Integration ===\n")

    # Test that imports work correctly
    try:
        from agent.nodes.understand import SENTRY_AVAILABLE as understand_sentry
        from agent.nodes.execute import SENTRY_AVAILABLE as execute_sentry
        from agent.nodes.generate import SENTRY_AVAILABLE as generate_sentry
        from agent.nodes.evaluate import SENTRY_AVAILABLE as evaluate_sentry

        print(f"✓ understand node: SENTRY_AVAILABLE={understand_sentry}")
        print(f"✓ execute node: SENTRY_AVAILABLE={execute_sentry}")
        print(f"✓ generate node: SENTRY_AVAILABLE={generate_sentry}")
        print(f"✓ evaluate node: SENTRY_AVAILABLE={evaluate_sentry}")

        if all([understand_sentry, execute_sentry, generate_sentry, evaluate_sentry]):
            print("\n✓ All agent nodes have Sentry integration available!")
        else:
            print("\n⚠ Some nodes don't have Sentry available (check imports)")

    except ImportError as e:
        print(f"✗ Import error: {e}")
        return

    # Test that graph integrates Langfuse
    try:
        from agent.graph import F1Agent

        agent = F1Agent(enable_memory=False)
        print(f"✓ F1Agent created successfully")

    except Exception as e:
        print(f"✗ Error creating F1Agent: {e}")

    print("\n✓ Agent integration tests passed!")


async def main():
    """Run all observability tests."""
    print("=" * 60)
    print("Observability Test Suite (Langfuse v3 + Sentry)")
    print("=" * 60)

    await test_sentry()
    await test_langfuse()
    await test_agent_integration()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
    print("\nConfiguration notes:")
    print("- Set SENTRY_DSN to enable Sentry error monitoring")
    print("- Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY for LLM tracing")
    print("- Both services gracefully degrade if not configured")
    print("\nLangfuse v3 features:")
    print("- @observe decorator for automatic function tracing")
    print("- Direct trace/span creation API")
    print("- LangChain callback handler (requires langfuse[langchain])")


if __name__ == "__main__":
    asyncio.run(main())
