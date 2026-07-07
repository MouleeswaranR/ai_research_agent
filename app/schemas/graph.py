"""Pydantic schemas for Dependency Graph execution."""

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.architecture import NodeType


class SymbolKind(str, Enum):
    FUNCTION = "function"
    CLASS = "class"
    CONST = "const"
    TYPE = "type"
    COMPONENT = "component"
    ROUTE = "route"
    DEFAULT = "default"


class Symbol(BaseModel):
    name: str
    kind: SymbolKind
    signature: str | None = None


class ImportRef(BaseModel):
    symbol: str
    from_path: str
    kind: SymbolKind = SymbolKind.DEFAULT


class NodeStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    GENERATED = "generated"
    FAILED = "failed"
    STUBBED = "stubbed"
    BLOCKED = "blocked"


class GraphNode(BaseModel):
    id: str
    path: str
    type: NodeType
    language: str | None = None
    purpose: str
    related_feature_ids: list[str] = Field(default_factory=list)
    planned_imports: list[ImportRef] = Field(default_factory=list)
    planned_exports: list[Symbol] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    retries: int = 0
    generated_code: str | None = None
    actual_exports: list[Symbol] = Field(default_factory=list)
    critique_history: list[str] = Field(default_factory=list)


class ProjectGraph(BaseModel):
    """Output of Planner Agent. Consumed by app/orchestrator/graph.py."""
    project_id: str
    nodes: dict[str, GraphNode]
    generation_levels: list[list[str]] = Field(default_factory=list)

    def validate_consistency(self) -> None:
        """Validate that planned_imports and depends_on are consistent across all nodes.
        
        Ensures every from_path in planned_imports also appears in depends_on,
        preventing silent dependency mismatches that would break topological ordering.
        
        Raises:
            ValueError: If any node has mismatched imports vs dependencies.
        """
        for node_id, node in self.nodes.items():
            # Extract paths from planned_imports that exist in the graph
            import_paths = {
                imp.from_path for imp in node.planned_imports
                if imp.from_path in self.nodes
            }
            dep_paths = set(node.depends_on)

            if import_paths != dep_paths:
                raise ValueError(
                    f"Node '{node_id}': planned_imports {import_paths} != depends_on {dep_paths}. "
                    f"Every import must be in depends_on and vice versa."
                )


class CodeFileResult(BaseModel):
    """Output of single node code generation."""
    code: str
