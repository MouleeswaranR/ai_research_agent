"""Tests for token tracker."""

from app.token_tracker import TokenUsage, TokenTracker


class TestTokenTracker:
    """Test token measurement and aggregation."""

    def test_record_usage(self):
        tracker = TokenTracker()
        usage = TokenUsage(
            agent_name="test_agent",
            model="test-model",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=200.0,
        )
        tracker.record(usage)
        assert tracker.total_input_tokens == 100
        assert tracker.total_output_tokens == 50

    def test_cost_estimate(self):
        usage = TokenUsage(
            agent_name="test",
            model="test",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
            latency_ms=100.0,
        )
        assert usage.cost_estimate_usd > 0

    def test_per_agent_summary(self):
        tracker = TokenTracker()
        for i in range(3):
            tracker.record(TokenUsage(
                agent_name="agent_a",
                model="m",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                latency_ms=10.0,
            ))
        tracker.record(TokenUsage(
            agent_name="agent_b",
            model="m",
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
            latency_ms=20.0,
        ))
        summary = tracker.summary()
        assert summary["total_calls"] == 4
        assert summary["per_agent"]["agent_a"]["calls"] == 3
        assert summary["per_agent"]["agent_b"]["calls"] == 1

    def test_empty_tracker(self):
        tracker = TokenTracker()
        assert tracker.total_input_tokens == 0
        assert tracker.total_cost_usd == 0.0
        assert tracker.summary()["total_calls"] == 0
