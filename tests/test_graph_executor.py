"""Unit tests for graph topological execution, cycle handling, and drift logging."""

import pytest
import asyncio
from unittest.mock import MagicMock

from app.schemas.architecture import NodeType
from app.schemas.graph import GraphNode, ProjectGraph, Symbol, SymbolKind, NodeStatus, CodeFileResult
from app.orchestrator.graph import compute_generation_levels, handle_cycles, execute_graph


def test_compute_generation_levels_dag():
    """Test diamond-shaped DAG returns correct topological levels."""
    # A -> B -> D, A -> C -> D
    nodes = {
        "A": GraphNode(id="A", path="A", type=NodeType.FILE, purpose="A", depends_on=[]),
        "B": GraphNode(id="B", path="B", type=NodeType.FILE, purpose="B", depends_on=["A"]),
        "C": GraphNode(id="C", path="C", type=NodeType.FILE, purpose="C", depends_on=["A"]),
        "D": GraphNode(id="D", path="D", type=NodeType.FILE, purpose="D", depends_on=["B", "C"]),
    }
    graph = ProjectGraph(project_id="test", nodes=nodes)
    levels = compute_generation_levels(graph)

    assert len(levels) == 3
    assert levels[0] == ["A"]
    assert set(levels[1]) == {"B", "C"}
    assert levels[2] == ["D"]


def test_handle_cycles_stubbing():
    """Test cyclic graph stubs node with fewest exports and generates valid levels."""
    # A -> B -> A (Cycle)
    # A has 2 planned exports, B has 1 planned export -> B should be stubbed
    nodes = {
        "A": GraphNode(
            id="A", path="A", type=NodeType.FILE, purpose="A", depends_on=["B"],
            planned_exports=[Symbol(name="fn1", kind=SymbolKind.FUNCTION), Symbol(name="fn2", kind=SymbolKind.FUNCTION)],
        ),
        "B": GraphNode(
            id="B", path="B", type=NodeType.FILE, purpose="B", depends_on=["A"],
            planned_exports=[Symbol(name="fn3", kind=SymbolKind.FUNCTION)],
        ),
    }
    graph = ProjectGraph(project_id="cycle_test", nodes=nodes)
    levels = compute_generation_levels(graph)

    assert graph.nodes["B"].status == NodeStatus.STUBBED
    assert len(levels) > 0


@pytest.mark.asyncio
async def test_execute_graph_export_drift_logging():
    """Test execute_graph logs export drift when actual exports differ from planned."""
    nodes = {
        "A": GraphNode(
            id="A", path="A.py", type=NodeType.FILE, language="python", purpose="A", depends_on=[],
            planned_exports=[Symbol(name="planned_func", kind=SymbolKind.FUNCTION)],
        ),
    }
    graph = ProjectGraph(project_id="drift_test", nodes=nodes)

    mock_tracer = MagicMock()
    mock_generator = MagicMock()
    mock_critique = MagicMock()
    mock_eval = MagicMock()

    class DummyLimiter:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass

    # Mock generator returning code with actual_func (differs from planned_func)
    parsed_result = CodeFileResult(code="def actual_func(): pass")

    async def mock_run_with_retry(*args, **kwargs):
        return parsed_result, None

    # Patch run_with_retry inside orchestrator
    import app.orchestrator.review_gate as rg
    orig_run_with_retry = rg.run_with_retry
    rg.run_with_retry = mock_run_with_retry

    try:
        await execute_graph(
            graph, mock_tracer, DummyLimiter(),
            mock_generator, mock_critique, mock_eval
        )
        assert mock_tracer.log_export_drift.called
    finally:
        rg.run_with_retry = orig_run_with_retry
