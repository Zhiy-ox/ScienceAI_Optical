"""Tests for LLMClient prompt caching and batch queue."""

from science_ai.services.llm_client import LLMClient


def test_prompt_caching_anthropic():
    """Anthropic system messages get cache_control added."""
    client = LLMClient()
    messages = [
        {"role": "system", "content": "You are a research assistant."},
        {"role": "user", "content": "Hello"},
    ]
    cached = client._apply_prompt_caching(messages, "claude-opus-4-6")
    assert cached[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in cached[1]


def test_prompt_caching_openai_passthrough():
    """OpenAI messages are returned unchanged (auto-caching)."""
    client = LLMClient()
    messages = [
        {"role": "system", "content": "You are a research assistant."},
        {"role": "user", "content": "Hello"},
    ]
    result = client._apply_prompt_caching(messages, "gpt-5.4")
    assert result == messages
    assert "cache_control" not in result[0]


def test_prompt_caching_unknown_model():
    """Unknown models pass through without modification."""
    client = LLMClient()
    messages = [{"role": "system", "content": "test"}]
    result = client._apply_prompt_caching(messages, "unknown-model")
    assert result == messages


def test_batch_queue():
    """Queue requests and check queue size."""
    client = LLMClient()
    assert client.batch_queue_size == 0

    cid = client.queue_batch_request(
        messages=[{"role": "user", "content": "test"}],
        task_type="paper_triage",
        agent_name="triage",
        session_id="s1",
    )
    assert client.batch_queue_size == 1
    assert isinstance(cid, str)

    # Queue another
    client.queue_batch_request(
        messages=[{"role": "user", "content": "test2"}],
        model="gpt-5.4",
        agent_name="triage",
        custom_id="custom-123",
    )
    assert client.batch_queue_size == 2


def test_batch_queue_custom_id():
    """Custom IDs are preserved in the queue."""
    client = LLMClient()
    cid = client.queue_batch_request(
        messages=[{"role": "user", "content": "test"}],
        model="gpt-5.4",
        custom_id="my-custom-id",
    )
    assert cid == "my-custom-id"
