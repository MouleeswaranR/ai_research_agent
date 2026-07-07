"""Tests for agent registry and base agent."""

import pytest
from app.agents import AGENT_REGISTRY, get_agent, list_agents


class TestAgentRegistry:
    """Test agent registration and factory."""

    def test_twelve_agents_registered(self):
        assert len(AGENT_REGISTRY) == 14

    def test_get_agent_returns_instance(self):
        agent = get_agent("product_strategist")
        assert agent.name == "product_strategist"

    def test_get_unknown_agent_raises(self):
        with pytest.raises(ValueError, match="Unknown agent"):
            get_agent("nonexistent")

    def test_list_agents_metadata(self):
        agents = list_agents()
        assert len(agents) == 14
        names = [a["name"] for a in agents]
        assert "code_reviewer" in names
        assert "code_generator" in names

    def test_code_reviewer_has_full_toolset(self):
        agents = list_agents()
        reviewer = next(a for a in agents if a["name"] == "code_reviewer")
        assert len(reviewer["tools"]) >= 6
        assert "ruff_lint" in reviewer["tools"]
        assert "bandit_scan" in reviewer["tools"]

    def test_code_generator_has_tools(self):
        agents = list_agents()
        gen = next(a for a in agents if a["name"] == "code_generator")
        assert "write_file" in gen["tools"]
        assert "execute_python" in gen["tools"]

    def test_strategist_has_no_tools(self):
        agents = list_agents()
        strat = next(a for a in agents if a["name"] == "product_strategist")
        assert len(strat["tools"]) == 0


class TestAgentTokenBudgets:
    """Verify token budgets are reasonable."""

    def test_reviewer_has_minimal_budget(self):
        agent = get_agent("code_reviewer")
        assert agent.max_tokens <= 512

    def test_generator_has_largest_budget(self):
        agent = get_agent("code_generator")
        assert agent.max_tokens >= 4096
