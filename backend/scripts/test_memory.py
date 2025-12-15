#!/usr/bin/env python3
"""Test script for the memory system.

Tests:
1. Redis SessionState - session creation, message history, context
2. Mem0 UserMemory - memory storage and retrieval (requires Ollama)

Run from the backend directory:
    python scripts/test_memory.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_session_state():
    """Test Redis session state."""
    print("\n" + "=" * 50)
    print("Testing Redis SessionState")
    print("=" * 50)

    from memory.session_state import SessionState

    session_state = SessionState(
        redis_host="redis",  # Use Docker service name
        redis_port=6379,
    )

    try:
        await session_state.initialize()
        print("✓ Connected to Redis")

        # Test session creation
        session_id = "test_session_123"
        user_id = "test_user_456"

        session = await session_state.create_session(
            session_id=session_id,
            user_id=user_id,
            metadata={"test": True},
        )
        print(f"✓ Created session: {session['session_id']}")

        # Test adding messages
        await session_state.add_message(
            session_id=session_id,
            role="user",
            content="Who won the Monaco 2024 race?",
        )
        await session_state.add_message(
            session_id=session_id,
            role="assistant",
            content="Charles Leclerc won the Monaco 2024 Grand Prix.",
        )
        print("✓ Added messages to history")

        # Test getting history
        history = await session_state.get_history(session_id, limit=10)
        print(f"✓ Retrieved history: {len(history)} messages")
        for msg in history:
            print(f"  - {msg['role']}: {msg['content'][:50]}...")

        # Test setting context
        await session_state.set_context(session_id, {
            "current_race": "Monaco 2024",
            "drivers": ["LEC", "SAI"],
            "query_type": "results",
        })
        print("✓ Set session context")

        # Test getting context
        context = await session_state.get_context(session_id)
        print(f"✓ Retrieved context: {context}")

        # Test updating context
        context = await session_state.update_context(session_id, {
            "additional_info": "Ferrari 1-2",
        })
        print(f"✓ Updated context: {context}")

        # Test cache
        await session_state.cache_set(session_id, "lap_data", {"lap_1": 1.23})
        cached = await session_state.cache_get(session_id, "lap_data")
        print(f"✓ Cache set/get: {cached}")

        # Cleanup
        await session_state.delete_session(session_id)
        print("✓ Cleaned up test session")

        # Health check
        healthy = await session_state.health_check()
        print(f"✓ Health check: {healthy}")

        await session_state.close()
        print("\n✓ Redis SessionState tests PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Redis SessionState test FAILED: {e}")
        return False


async def test_user_memory():
    """Test Mem0 user memory."""
    print("\n" + "=" * 50)
    print("Testing Mem0 UserMemory")
    print("=" * 50)

    from memory.user_memory import UserMemory

    user_memory = UserMemory(
        qdrant_host="qdrant",  # Use Docker service name
        qdrant_port=6333,
        collection_name="test_user_memories",
        llm_provider="ollama",
        llm_config={"ollama_base_url": "http://ollama:11434"},
    )

    try:
        user_memory.initialize()
        print("✓ Initialized UserMemory with Ollama")

        user_id = "test_user_mem0"

        # Test adding memory
        messages = [
            {"role": "user", "content": "I'm a huge Ferrari fan and my favorite driver is Charles Leclerc."},
            {"role": "assistant", "content": "Great! I'll remember that you support Ferrari and Charles Leclerc is your favorite driver."},
        ]

        result = await user_memory.add_memory(
            user_id=user_id,
            messages=messages,
            metadata={"source": "test"},
        )
        print(f"✓ Added memory: {result}")

        # Test searching memories
        memories = await user_memory.search_memories(
            user_id=user_id,
            query="favorite driver",
            limit=5,
        )
        print(f"✓ Found {len(memories)} memories for 'favorite driver'")
        for mem in memories:
            # Handle both string and dict return types
            if isinstance(mem, str):
                print(f"  - {mem}")
            else:
                memory_text = mem.get("memory", mem.get("text", str(mem)))
                print(f"  - {memory_text}")

        # Test getting all memories
        all_memories = await user_memory.get_all_memories(user_id)
        print(f"✓ Total memories for user: {len(all_memories)}")

        # Test get_user_context
        context = await user_memory.get_user_context(user_id, "What about Leclerc?")
        print(f"✓ User context:\n{context}")

        # Cleanup - delete all memories for test user
        await user_memory.delete_all_memories(user_id)
        print("✓ Cleaned up test memories")

        # Health check
        healthy = user_memory.health_check()
        print(f"✓ Health check: {healthy}")

        print("\n✓ Mem0 UserMemory tests PASSED")
        return True

    except Exception as e:
        print(f"\n✗ Mem0 UserMemory test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all memory tests."""
    print("\n" + "#" * 60)
    print("# F1 RIA Memory System Tests")
    print("#" * 60)

    results = {}

    # Test Redis SessionState
    results["redis"] = await test_session_state()

    # Test Mem0 UserMemory (requires Ollama)
    print("\nNote: Mem0 test requires Ollama to be running.")
    try:
        results["mem0"] = await test_user_memory()
    except Exception as e:
        print(f"Mem0 test skipped or failed: {e}")
        results["mem0"] = False

    # Summary
    print("\n" + "#" * 60)
    print("# Test Summary")
    print("#" * 60)
    for name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {name}: {status}")

    all_passed = all(results.values())
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
