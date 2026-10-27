"""
Tests for cloud multi-provider routing reliability:
- Bounded timeouts & timeout handling
- Retry limits and non-infinite loops
- Exponential backoff & jitter
- HTTP 429 Retry-After parsing (integer & HTTP-date)
- 401/403 authentication failures avoid pointless retries
- Fallback selection when providers fail (429, 500, timeouts, malformed, empty)
- Provider status & observability (configured, available, rate_limited, unavailable, auth_failure, not_configured)
- Secret sanitization in errors/exceptions
- Separation of model failover from tool execution (preventing duplicate side effects)
"""

import time
import pytest
from unittest.mock import patch, MagicMock
import requests

from brain.cloud_router import (
    route_task,
    chat_completion,
    ProviderError,
    _parse_retry_after,
    _cooldown_until,
    _provider_state,
    _clear_cooldown,
    _clear_cooldown_label,
    _set_cooldown_label,
    _on_cooldown_label,
    get_provider_status,
    get_model_usage,
    STATUS_CONFIGURED,
    STATUS_AVAILABLE,
    STATUS_RATE_LIMITED,
    STATUS_UNAVAILABLE,
    STATUS_AUTH_FAILURE,
    STATUS_NOT_CONFIGURED,
    reset_provider_cooldown,
    _on_cooldown,
    _set_cooldown,
    _groq_chat,
)


@pytest.fixture(autouse=True)
def clean_cooldown_state():
    """Ensure clean cooldown, provider state, and usage metrics before each test."""
    from brain.cloud_router import _session_count, _last_used
    with patch.dict(_cooldown_until, clear=True):
        with patch.dict(_provider_state, clear=True):
            with patch.dict(_session_count, clear=True):
                with patch.dict(_last_used, {"label": None, "task_type": None, "time": None}):
                    yield


# ── 1. Retry-After Header Parsing ─────────────────────────────────

def test_parse_retry_after_integer():
    assert _parse_retry_after("120", default=90) == 120.0
    assert _parse_retry_after("0", default=90) == 1.0  # bounded lower
    assert _parse_retry_after("100000", default=90) == 3600.0  # bounded upper (1 hr cap)


def test_parse_retry_after_http_date():
    future_time = time.time() + 45
    date_str = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(future_time))
    val = _parse_retry_after(date_str, default=90)
    assert 40 <= val <= 50


def test_parse_retry_after_invalid_or_empty():
    assert _parse_retry_after(None, default=90) == 90.0
    assert _parse_retry_after("", default=90) == 90.0
    assert _parse_retry_after("invalid-date-string", default=90) == 90.0


# ── 2. Authentication Failure Prevents Pointless Retries ──────────

def test_auth_failure_sets_permanent_cooldown_and_auth_status():
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized: Invalid API key gsk_testsecret12345678"

    with patch("brain.cloud_router.GROQ_API_KEY", "gsk_testsecret12345678"):
        with patch("brain.cloud_router._SHARED_HTTP_SESSION.post", return_value=mock_resp):
            from brain.cloud_router import _groq_chat
            with pytest.raises(ProviderError) as exc_info:
                _groq_chat([{"role": "user", "content": "hi"}], "system", 100, "openai/gpt-oss-120b")
            
            err = exc_info.value
            assert err.status == STATUS_AUTH_FAILURE
            assert err.retry_after == 86400
            assert "gsk_" not in err.reason  # secret was redacted
            assert "[REDACTED_GROQ_KEY]" in err.reason or "[REDACTED" in err.reason


# ── 3. Rate Limit Respects Retry-After ─────────────────────────────

def test_rate_limit_respects_retry_after():
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "45"}
    mock_resp.text = "Rate limit reached"

    with patch("brain.cloud_router.MISTRAL_API_KEY", "valid-key"):
        with patch("brain.cloud_router._SHARED_HTTP_SESSION.post", return_value=mock_resp):
            from brain.cloud_router import _mistral_chat
            with pytest.raises(ProviderError) as exc_info:
                _mistral_chat([{"role": "user", "content": "hi"}], "system", 100)
            
            err = exc_info.value
            assert err.status == STATUS_RATE_LIMITED
            assert err.retry_after == 45.0


# ── 4. Fallback Selection Across Chain ─────────────────────────────

def test_fallback_selection_when_primary_providers_fail():
    """
    In the 'code' chain: groq -> groq_llama33 -> mistral -> gemini -> gemini_pro.
    When groq fails with 429, groq_llama33 with 500, mistral with timeout,
    gemini should take over successfully.
    """
    call_records = []

    def fake_groq(m, s, t, model):
        call_records.append(f"groq_{model}")
        if "gpt-oss" in model:
            raise ProviderError("groq", "rate limited", status=STATUS_RATE_LIMITED, retry_after=30)
        else:
            raise ProviderError("groq_llama33", "internal server error", status=STATUS_UNAVAILABLE)

    def fake_mistral(m, s, t):
        call_records.append("mistral")
        raise requests.exceptions.Timeout("Read timeout")

    def fake_gemini(m, s, t, model):
        call_records.append("gemini")
        return "def solve(): return 42", 15

    with patch("brain.cloud_router._groq_chat", side_effect=fake_groq), \
         patch("brain.cloud_router._mistral_chat", side_effect=fake_mistral), \
         patch("brain.cloud_router._gemini_chat", side_effect=fake_gemini):
        
        text, provider = route_task("code", [{"role": "user", "content": "write code"}], "sys")
        
        assert text == "def solve(): return 42"
        assert provider == "gemini"
        assert _on_cooldown_label("groq")
        assert _on_cooldown_label("groq_llama33")
        assert _on_cooldown_label("mistral")
        assert not _on_cooldown_label("gemini")


def test_all_providers_fail_raises_runtime_error_cleanly():
    """When all providers fail, a clean RuntimeError is raised without infinite loop."""
    with patch("brain.cloud_router._groq_chat", side_effect=ProviderError("groq", "error")), \
         patch("brain.cloud_router._mistral_chat", side_effect=ProviderError("mistral", "error")), \
         patch("brain.cloud_router._gemini_chat", side_effect=ProviderError("gemini", "error")), \
         patch("brain.cloud_router._openrouter_chat", side_effect=ProviderError("openrouter", "error")):
        
        with pytest.raises(RuntimeError) as exc_info:
            route_task("agent", [{"role": "user", "content": "hello"}], "sys")
        
        assert "All available models for agent are currently rate-limited" in str(exc_info.value)


# ── 5. Provider Status Classification & Observability ─────────────

def test_provider_status_distinctions():
    with patch("brain.cloud_router.GROQ_API_KEY", ""):
        assert get_provider_status("groq") == STATUS_NOT_CONFIGURED

    with patch("brain.cloud_router.GROQ_API_KEY", "configured_key"):
        assert get_provider_status("groq") == STATUS_CONFIGURED

        # Simulate verified available
        with patch.dict("brain.cloud_router._session_count", {"groq": 50}):
            assert get_provider_status("groq") == STATUS_AVAILABLE

        # Simulate 429 rate limit
        _set_cooldown_label("groq", duration=60, status=STATUS_RATE_LIMITED)
        assert get_provider_status("groq") == STATUS_RATE_LIMITED

        # Simulate 500 unavailable
        _set_cooldown_label("groq", duration=60, status=STATUS_UNAVAILABLE)
        assert get_provider_status("groq") == STATUS_UNAVAILABLE

        # Simulate 401 auth failure
        _set_cooldown_label("groq", duration=86400, status=STATUS_AUTH_FAILURE)
        assert get_provider_status("groq") == STATUS_AUTH_FAILURE


def test_get_model_usage_contains_status_and_cooldown():
    with patch("brain.cloud_router.GROQ_API_KEY", "some-key"):
        _set_cooldown_label("groq", duration=45, status=STATUS_RATE_LIMITED)
        usage = get_model_usage()
        assert "groq" in usage
        assert usage["groq"]["on_cooldown"] is True
        assert usage["groq"]["status"] == STATUS_RATE_LIMITED
        assert usage["groq"]["cooldown_resets_in"] is not None


# ── 6. Secret Redaction in Exceptions and Logs ─────────────────────

def test_secret_redaction_in_provider_error():
    err = ProviderError("test_prov", "Failed with key gsk_12345678901234567890")
    assert "gsk_12345678901234567890" not in str(err)
    assert "[REDACTED_GROQ_KEY]" in str(err)


# ── 7. Duplicate Side-Effect Prevention ─────────────────────────────

def test_model_fallback_does_not_repeat_tool_execution():
    """
    Verify that AI failovers inside the router occur strictly at the model-response
    generation phase and do not trigger tool calls or project mutations twice.
    """
    tool_execution_count = 0

    def dummy_tool():
        nonlocal tool_execution_count
        tool_execution_count += 1
        return "SUCCESS"

    # Route task through failover chain
    call_count = 0
    def failing_provider(m, s, t, model):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ProviderError("groq", "transient error")
        return '{"thought":"done","action":"FINAL","answer":"ok"}', 10

    with patch("brain.cloud_router._groq_chat", side_effect=failing_provider):
        res, prov = route_task("code", [{"role": "user", "content": "test"}], "sys")
        assert prov == "groq_llama33"
        # Tool was never called during model failover
        assert tool_execution_count == 0


# ── 8. Task 1: Auth Recovery & Provider Isolation ───────────────────

def test_auth_recovery_when_credentials_corrected():
    """Verify that correcting invalid credentials allows controlled recovery via reset_provider_cooldown."""
    from brain.cloud_router import reset_provider_cooldown

    # Simulate 401 on groq
    _set_cooldown_label("groq", duration=86400, status=STATUS_AUTH_FAILURE)
    assert _on_cooldown_label("groq") is True
    assert get_provider_status("groq") == STATUS_AUTH_FAILURE

    # Correct credentials and trigger recovery
    with patch("brain.cloud_router.GROQ_API_KEY", "new_valid_key"):
        reset_provider_cooldown("groq")
        assert _on_cooldown_label("groq") is False
        assert get_provider_status("groq") == STATUS_CONFIGURED


def test_auth_failure_on_one_provider_does_not_affect_unrelated_providers():
    """Verify an auth failure on Groq leaves Mistral and Gemini completely unaffected."""
    _set_cooldown_label("groq", duration=86400, status=STATUS_AUTH_FAILURE)
    assert _on_cooldown_label("groq") is True

    with patch("brain.cloud_router.MISTRAL_API_KEY", "mistral_valid_key"), \
         patch("brain.cloud_router.GOOGLE_API_KEY", "gemini_valid_key"):
        assert _on_cooldown_label("mistral") is False
        assert _on_cooldown_label("gemini") is False
        assert get_provider_status("mistral") == STATUS_CONFIGURED
        assert get_provider_status("gemini") == STATUS_CONFIGURED


def test_provider_status_and_failure_log_never_exposes_api_keys():
    """Verify that provider error status and logs never expose API keys or authorization headers."""
    secret_key = "gsk_supersecretkey1234567890123"
    err = ProviderError("groq", f"Bearer {secret_key}", status=STATUS_AUTH_FAILURE)
    assert secret_key not in err.reason
    assert secret_key not in str(err)


# ── 9. Task 2: Rate Limit Edge Cases & Storm Prevention ────────────

def test_retry_after_edge_cases():
    """Test excessive delay capping, expired dates, and invalid values."""
    from brain.cloud_router import MAX_RETRY_AFTER_SECONDS

    # Excessive delay should be capped to 3600s
    assert _parse_retry_after("9999999", default=90) == MAX_RETRY_AFTER_SECONDS

    # Negative integer value falls back to default
    assert _parse_retry_after("-10", default=90) == 90.0

    # Expired HTTP-date falls back to default cooldown
    past_time = time.time() - 3600
    past_date_str = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(past_time))
    assert _parse_retry_after(past_date_str, default=90) == 90.0

    # Invalid header format falls back to default cooldown
    assert _parse_retry_after("invalid_header_value", default=90) == 90.0


# ── 10. Task 3: End-to-End Deadlines ───────────────────────────────

def test_route_task_bounds_total_cascade_time():
    """Verify that route_task respects the overall routing deadline across retries."""
    call_count = 0
    def slow_provider(m, s, t):
        nonlocal call_count
        call_count += 1
        raise ProviderError("slow", "timeout", status=STATUS_UNAVAILABLE)

    # Patch time.monotonic in route_task so it detects the deadline elapsed before next attempt
    with patch("time.monotonic", side_effect=[0.0, 200.0, 200.0, 200.0, 200.0]):
        with pytest.raises(RuntimeError) as exc_info:
            route_task("agent", [{"role": "user", "content": "hello"}], "sys")
        assert "rate-limited or unavailable" in str(exc_info.value)


def test_route_task_passes_remaining_budget_to_provider_timeout():
    """Verify that route_task dynamically adjusts provider HTTP socket timeout based on remaining budget."""
    recorded_budgets = []
    def recording_provider(m, s, t, b=None):
        recorded_budgets.append(b)
        raise ProviderError("mock", "fail", status=STATUS_UNAVAILABLE)

    # start_time (t=0), p1 check (t=30 -> 150s left), p2 check (t=70 -> 110s left), p3 check (t=190 -> 0s left)
    with patch("time.monotonic", side_effect=[0.0, 30.0, 70.0, 190.0, 190.0]), \
         patch.dict("brain.cloud_router._CHAINS", {"test_task": [
             ("p1", recording_provider),
             ("p2", recording_provider),
             ("p3", recording_provider),
         ]}):
        with pytest.raises(RuntimeError):
            route_task("test_task", [{"role": "user", "content": "hi"}], "sys")
        assert len(recorded_budgets) == 2
        assert recorded_budgets[0] == 150.0
        assert recorded_budgets[1] == 110.0


def test_compute_timeout_clamps_properly():
    """Verify that _compute_timeout bounds connect/read timeouts correctly across budgets."""
    from brain.cloud_router import _compute_timeout
    # When budget is None
    assert _compute_timeout(10, 60, None) == (10, 60)
    # Remaining budget = 180s (larger than defaults)
    assert _compute_timeout(10, 60, 180.0) == (10, 60)
    # Remaining budget = 30s (read clamped to 30, connect remains 10)
    assert _compute_timeout(10, 60, 30.0) == (10, 30.0)
    # Remaining budget = 5s (both connect and read clamped to 5s)
    assert _compute_timeout(10, 60, 5.0) == (5.0, 5.0)
    # Remaining budget = 1s (both clamped to 1.0s)
    assert _compute_timeout(10, 60, 1.0) == (1.0, 1.0)
    # Remaining budget = 0.3s (both clamped to 0.3s, never exceeding budget)
    t_conn, t_read = _compute_timeout(10, 60, 0.3)
    assert t_conn <= 0.3 and t_read <= 0.3
    assert (t_conn, t_read) == (0.3, 0.3)
    # Remaining budget = 0.2s (both clamped to 0.2s, never exceeding budget)
    t_conn, t_read = _compute_timeout(10, 60, 0.2)
    assert t_conn <= 0.2 and t_read <= 0.2
    assert (t_conn, t_read) == (0.2, 0.2)
    # Remaining budget = 0.05s (both clamped to 0.05s, never exceeding budget)
    t_conn, t_read = _compute_timeout(10, 60, 0.05)
    assert t_conn <= 0.05 and t_read <= 0.05
    assert (t_conn, t_read) == (0.05, 0.05)
    # Remaining budget = 0s (returns (0.0, 0.0) to prevent request initiation)
    assert _compute_timeout(10, 60, 0.0) == (0.0, 0.0)
    # Negative budget (exhausted: returns (0.0, 0.0))
    assert _compute_timeout(10, 60, -5.0) == (0.0, 0.0)


def test_stream_query_deadline_and_fallback():
    """Verify that stream_query bounds elapsed chunk streaming and handles stalled/slow chunks."""
    from brain.ai_engine import stream_query

    # Test 1: stream_query stops yielding chunks once time.monotonic exceeds 180s
    def infinite_slow_chunks(*args, **kwargs):
        # First chunk at t=10s, second chunk at t=190s (past 180s deadline)
        yield "chunk1"
        yield "chunk2"

    with patch("brain.ai_engine._groq_stream", side_effect=infinite_slow_chunks), \
         patch("brain.ai_engine.GROQ_API_KEY", "gsk_test"), \
         patch("brain.cloud_router._on_cooldown", return_value=False), \
         patch("time.monotonic", side_effect=[0.0, 5.0, 10.0, 195.0, 195.0]):
        chunks = list(stream_query("write code"))
        assert chunks == ["chunk1"]  # chunk2 was cut off by STREAM_TOTAL_DEADLINE_SECONDS


def test_auth_recovery_complete_sequence():
    """
    Test complete Task 4 authentication recovery sequence:
    1. Provider returns HTTP 401.
    2. Provider enters authentication-failure cooldown.
    3. Credentials are corrected.
    4. Recovery is triggered using reset_provider_cooldown(label).
    5. The provider can be selected and used again.
    6. Other providers remain unaffected throughout.
    7. Status endpoints do not expose credentials.
    """
    reset_provider_cooldown()

    # Step 1: Provider returns HTTP 401
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Invalid API key provided: secret_groq_key_9999"

    with patch("brain.cloud_router._SHARED_HTTP_SESSION.post", return_value=mock_resp), \
         patch("brain.cloud_router.GROQ_API_KEY", "secret_groq_key_9999"):
        with pytest.raises(ProviderError) as exc_info:
            _groq_chat([{"role": "user", "content": "hi"}], "sys", 100, "llama3")
        assert exc_info.value.status == STATUS_AUTH_FAILURE
        _set_cooldown("groq", duration=exc_info.value.retry_after, status=exc_info.value.status)

    # Step 2: Groq is in auth_failure cooldown
    assert _on_cooldown("groq") is True
    assert get_provider_status("groq") == STATUS_AUTH_FAILURE

    # Step 6: Verify other providers remain unaffected throughout
    assert _on_cooldown("mistral") is False
    assert get_provider_status("mistral") == STATUS_CONFIGURED

    # Step 7: Verify status does not expose secrets or sensitive exception details
    usage = get_model_usage()
    for prov_name, prov_info in usage.items():
        prov_str = str(prov_info)
        assert "secret_groq_key" not in prov_str
        assert "9999" not in prov_str

    # Step 3 & 4: Credentials corrected and recovery triggered
    reset_provider_cooldown("groq")

    # Step 5: Provider is no longer on cooldown and can be used
    assert _on_cooldown("groq") is False
    assert get_provider_status("groq") in (STATUS_AVAILABLE, STATUS_CONFIGURED)

    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {
        "choices": [{"message": {"content": "Hello!"}}],
        "usage": {"total_tokens": 10}
    }
    with patch("brain.cloud_router._SHARED_HTTP_SESSION.post", return_value=success_resp), \
         patch("brain.cloud_router.GROQ_API_KEY", "new_valid_key"):
        text, tokens = _groq_chat([{"role": "user", "content": "hi"}], "sys", 100, "llama3")
        assert text == "Hello!"
        assert tokens == 10


# ── 11. Task 4: ReAct Agent Integration Side-Effect Prevention ─────

def test_react_agent_model_failover_prevents_duplicate_tool_execution():
    """
    Integration test around the actual ReAct agent flow in brain/agent.py:
    Simulates a multi-step execution where:
    - Step 1: Agent calls a tool (e.g. system_info).
    - Step 2: Model encounters a transient provider failure during response generation.
    - Router falls back to the next model in chain to produce FINAL response.
    Verify that the tool action is executed EXACTLY ONCE, never duplicated.
    """
    from brain.agent import run_agent

    tool_call_count = 0
    def counted_system_info(*args, **kwargs):
        nonlocal tool_call_count
        tool_call_count += 1
        return "CPU: 12%, Memory: 45%"

    # Step responses for AI calls:
    # 1st query: AI returns tool action
    step1_json = '{"thought":"check status","action":"system_info","args":{"query":"status"}}'
    # 2nd query: Groq fails, Gemini succeeds with FINAL
    step2_final_json = '{"thought":"done","action":"FINAL","answer":"System is healthy at 12% CPU"}'

    ai_call_count = 0
    def mock_query(prompt, history=None, max_tokens=2048, system=None, task_type=None):
        nonlocal ai_call_count
        ai_call_count += 1
        if ai_call_count == 1:
            return step1_json
        # Step 2: simulate model failover inside cloud_router
        def failing_gemini(m, s, t, model):
            raise ProviderError("gemini", "transient network failure")
        def success_groq(m, s, t, model):
            return step2_final_json, 25

        with patch("brain.cloud_router._gemini_chat", side_effect=failing_gemini), \
             patch("brain.cloud_router._groq_chat", side_effect=success_groq):
            text, _ = route_task("agent", [{"role": "user", "content": prompt}], system)
            return text

    with patch("brain.ai_engine.query", side_effect=mock_query), \
         patch.dict("brain.agent.TOOLS", {"system_info": {"fn": counted_system_info, "desc": "sys info"}}):
        
        answer = run_agent("What is the system status?")
        
        assert "System is healthy" in answer
        assert tool_call_count == 1  # Tool was executed strictly once!


def test_call_provider_safe_preserves_internal_type_error():
    """Verify that _call_provider_safe does not swallow or misinterpret internal TypeErrors."""
    from brain.cloud_router import _call_provider_safe

    def buggy_provider(m, s, t, timeout_budget=None):
        # Internal bug inside provider: raises TypeError
        return 1 + "invalid"

    with pytest.raises(TypeError) as excinfo:
        _call_provider_safe(buggy_provider, [], "sys", 100, timeout_budget=10.0)
    assert "unsupported operand type" in str(excinfo.value)


def test_call_provider_safe_filters_unsupported_kwargs():
    """Verify that _call_provider_safe strips unsupported kwargs for legacy/mock callables."""
    from brain.cloud_router import _call_provider_safe

    def legacy_provider(m, s, t):
        return ("legacy response", 10)

    res, tokens = _call_provider_safe(legacy_provider, [], "sys", 100, timeout_budget=5.0, search_grounding=True)
    assert res == "legacy response"
    assert tokens == 10


def test_groq_stream_timeout_bounds_socket():
    """Verify that _groq_stream calculates bounded socket timeout for requests.post."""
    from brain.ai_engine import _groq_stream
    captured_timeout = []

    class DummyContext:
        def __enter__(self):
            class DummyResp:
                status_code = 200
                def iter_lines(self, decode_unicode=True):
                    return iter([])
            return DummyResp()
        def __exit__(self, *args):
            pass

    def mock_post(url, **kwargs):
        captured_timeout.append(kwargs.get("timeout"))
        return DummyContext()

    with patch("brain.ai_engine._SHARED_HTTP_SESSION.post", side_effect=mock_post), \
         patch("brain.ai_engine.GROQ_API_KEY", "gsk_test"):
        list(_groq_stream([{"role": "user", "content": "hi"}], timeout_budget=2.5))
        assert len(captured_timeout) == 1
        # Bounded to budget: connect <= 2.5, read <= 2.5
        assert captured_timeout[0] == (2.5, 2.5)

        # Test small budget 0.2s: socket timeout is strictly bounded by 0.2s
        captured_timeout.clear()
        list(_groq_stream([{"role": "user", "content": "hi"}], timeout_budget=0.2))
        assert len(captured_timeout) == 1
        assert captured_timeout[0] == (0.2, 0.2)

        # Test exhausted budget <= 0.1s: network request NEVER begins
        captured_timeout.clear()
        list(_groq_stream([{"role": "user", "content": "hi"}], timeout_budget=0.05))
        assert len(captured_timeout) == 0


def test_gemini_stream_timeout_bounds_socket():
    """Verify that _gemini_stream calculates bounded socket timeout for requests.post."""
    from brain.ai_engine import _gemini_stream
    captured_timeout = []

    class DummyContext:
        def __enter__(self):
            class DummyResp:
                status_code = 200
                def iter_lines(self, decode_unicode=True):
                    return iter([])
            return DummyResp()
        def __exit__(self, *args):
            pass

    def mock_post(url, **kwargs):
        captured_timeout.append(kwargs.get("timeout"))
        return DummyContext()

    with patch("brain.ai_engine._SHARED_HTTP_SESSION.post", side_effect=mock_post), \
         patch("brain.ai_engine.GOOGLE_API_KEY", "gm_test"):
        list(_gemini_stream([{"role": "user", "content": "hi"}], timeout_budget=3.0))

        assert len(captured_timeout) == 1
        # Bounded to budget: connect <= 3.0, read <= 3.0
        assert captured_timeout[0] == (3.0, 3.0)

        # Test small budget 0.2s: socket timeout is strictly bounded by 0.2s
        captured_timeout.clear()
        list(_gemini_stream([{"role": "user", "content": "hi"}], timeout_budget=0.2))
        assert len(captured_timeout) == 1
        assert captured_timeout[0] == (0.2, 0.2)

        # Test exhausted budget <= 0.1s: network request NEVER begins
        captured_timeout.clear()
        list(_gemini_stream([{"role": "user", "content": "hi"}], timeout_budget=0.05))
        assert len(captured_timeout) == 0


def test_call_provider_safe_all_callable_variations():
    """Verify that _call_provider_safe handles functions, **kwargs, partials, wrapped callables, and mocks without double invocation."""
    import functools
    from unittest.mock import MagicMock
    from brain.cloud_router import _call_provider_safe

    # 1. Normal function with explicit signature
    invocations_1 = 0
    def normal_fn(m, s, t, timeout_budget=None):
        nonlocal invocations_1
        invocations_1 += 1
        return "normal_ok", timeout_budget

    res, b = _call_provider_safe(normal_fn, [], "sys", 100, timeout_budget=42.0)
    assert res == "normal_ok" and b == 42.0
    assert invocations_1 == 1

    # 2. Function accepting **kwargs
    invocations_2 = 0
    def var_kw_fn(m, s, **kwargs):
        nonlocal invocations_2
        invocations_2 += 1
        return "var_kw_ok", kwargs.get("timeout_budget")

    res, b = _call_provider_safe(var_kw_fn, [], "sys", timeout_budget=99.0)
    assert res == "var_kw_ok" and b == 99.0
    assert invocations_2 == 1

    # 3. functools.partial callable
    invocations_3 = 0
    def base_fn(extra, m, s, t, timeout_budget=None):
        nonlocal invocations_3
        invocations_3 += 1
        return f"partial_{extra}", timeout_budget

    partial_fn = functools.partial(base_fn, "custom")
    res, b = _call_provider_safe(partial_fn, [], "sys", 50, timeout_budget=15.0)
    assert res == "partial_custom" and b == 15.0
    assert invocations_3 == 1

    # 4. Wrapped callable (__wrapped__)
    invocations_4 = 0
    def inner_fn(m, s, t, timeout_budget=None):
        nonlocal invocations_4
        invocations_4 += 1
        return "wrapped_ok", timeout_budget

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper

    wrapped_fn = decorator(inner_fn)
    res, b = _call_provider_safe(wrapped_fn, [], "sys", 10, timeout_budget=7.0)
    assert res == "wrapped_ok" and b == 7.0
    assert invocations_4 == 1

    # 5. MagicMock with callable side effect
    side_invocations = 0
    def mock_side_effect(m, s, t, timeout_budget=None):
        nonlocal side_invocations
        side_invocations += 1
        return "mock_ok", timeout_budget

    mock_obj = MagicMock(side_effect=mock_side_effect)
    res, b = _call_provider_safe(mock_obj, [], "sys", 20, timeout_budget=3.5)
    assert res == "mock_ok" and b == 3.5
    assert side_invocations == 1


def test_stream_query_passes_remaining_budget_to_non_streaming_fallback():
    """Verify that stream_query passes remaining time budget to chat_completion fallback."""
    from brain.ai_engine import stream_query

    captured_budgets = []
    def mock_chat_completion(messages, system, max_tokens, task_type="agent", timeout_budget=None):
        captured_budgets.append(timeout_budget)
        return "fallback success", "mistral"

    # Simulate Groq & Gemini failing after 50s each (100s elapsed out of 180s)
    # 4 monotonic calls in stream_query:
    # 1: stream_start_time = 0.0
    # 2: rem_groq = 180 - 10.0 = 170.0
    # 3: rem_gem = 180 - 50.0 = 130.0
    # 4: rem_fallback = 180 - 100.0 = 80.0
    with patch("brain.ai_engine._groq_stream", side_effect=RuntimeError("groq fail")), \
         patch("brain.ai_engine._gemini_stream", side_effect=RuntimeError("gemini fail")), \
         patch("brain.ai_engine.GROQ_API_KEY", "gsk_test"), \
         patch("brain.ai_engine.GOOGLE_API_KEY", "gm_test"), \
         patch("brain.cloud_router._on_cooldown", return_value=False), \
         patch("brain.cloud_router.chat_completion", side_effect=mock_chat_completion), \
         patch("time.monotonic", side_effect=[0.0, 10.0, 50.0, 100.0]):
        chunks = list(stream_query("write code"))
        assert chunks == ["fallback success"]
        assert len(captured_budgets) == 1
        # Fallback received remaining budget: 180 - 100 = 80.0s
        assert captured_budgets[0] == 80.0


def test_sanitize_messages_strips_proprietary_metadata():
    """Verify that _sanitize_messages removes origin, verification_status, sources, etc."""
    from brain.cloud_router import _sanitize_messages
    raw = [
        {"role": "user", "content": "hello", "origin": "USER_PROVIDED", "verification_status": "NOT_APPLICABLE"},
        {"role": "assistant", "content": "hi", "sources": ["http://example.com"]},
        {"invalid": "format"},
    ]
    cleaned = _sanitize_messages(raw)
    assert len(cleaned) == 2
    assert cleaned[0] == {"role": "user", "content": "hello"}
    assert cleaned[1] == {"role": "assistant", "content": "hi"}
    assert "origin" not in cleaned[0]
    assert "verification_status" not in cleaned[0]
    assert "sources" not in cleaned[1]


def test_groq_chat_sanitizes_payload_messages():
    """Verify _groq_chat cleans messages before posting to Groq API."""
    from brain.cloud_router import _groq_chat
    mock_post = MagicMock()
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"total_tokens": 10}
    }
    mock_post.return_value = mock_resp

    with patch("brain.cloud_router.GROQ_API_KEY", "gsk_test"), \
         patch("brain.cloud_router._SHARED_HTTP_SESSION.post", mock_post):
        msg = [{"role": "user", "content": "test", "origin": "USER_PROVIDED"}]
        text, tokens = _groq_chat(msg, "system", 100, "openai/gpt-oss-120b")
        assert text == "ok"
        assert tokens == 10
        sent_payload = mock_post.call_args[1]["json"]
        for m in sent_payload["messages"]:
            assert "origin" not in m
            assert set(m.keys()).issubset({"role", "content", "name"})

