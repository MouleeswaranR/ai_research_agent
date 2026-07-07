You are working inside an existing repository for "Auto Dev Company" — an autonomous
multi-agent software builder (FastAPI + 14 agents + 5-phase pipeline, currently using a
single NVIDIA NIM model with Groq failover, structure as documented in README.md).

Every change below is ADDITIVE or an IN-PLACE EXTENSION of a file that already exists.
Do not rename, remove, reorder, or restructure anything not explicitly listed here.

## Goal
Extend Phase 1 (Planning & Architecture) so its five existing agents produce validated
Pydantic schemas instead of free text, composing into one project-wide dependency graph.
Change Phase 2's Code Generator loop to execute that graph in topological order (one file
at a time, dependencies first) instead of generating code from a flat plan. Add per-agent
NVIDIA NIM model routing. Everything must stay backward compatible behind a feature flag.

## Hard constraints (from CLAUDE.md — do not violate)
- Every file stays under 150 lines; every function stays under 30 lines, single-responsibility.
  Split new logic across multiple files/functions rather than growing one file past the limit.
- Product Strategist, Project Manager, System Architect, Security Architect, and Planner Agent
  keep their current names and position in Phase 1. No new agents are added.
- `app/orchestrator/graph.py` and `app/orchestrator/review_gate.py` are extended, not replaced —
  their existing exported functions/classes must keep working for any Phase 3/4 caller.
- Add `ENABLE_GRAPH_PIPELINE: bool = False` to `app/config.py`. When `False`, the pipeline
  behaves exactly as it does today, unmodified. When `True`, Phase 1 produces the new schemas
  and Phase 2 runs through the Graph Executor described below.

---

## 1. NEW FILE: app/schemas/architecture.py

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TechStack(BaseModel):
    frontend: Optional[str] = None
    backend: Optional[str] = None
    database: Optional[str] = None
    devops: Optional[str] = None
    rationale: str


class ElevatedSpec(BaseModel):
    """Output of Product Strategist."""
    original_idea: str
    project_title: str
    elevated_description: str
    problem_statement: str
    target_users: list[str]
    tech_stack: TechStack
    non_functional_requirements: list[str] = Field(default_factory=list)


class Priority(str, Enum):
    P0 = "must_have"
    P1 = "should_have"
    P2 = "nice_to_have"


class Layer(str, Enum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    SHARED = "shared"
    DEVOPS = "devops"


class Feature(BaseModel):
    id: str
    name: str
    description: str
    user_story: str
    acceptance_criteria: list[str]
    priority: Priority
    layer: Layer
    depends_on: list[str] = Field(default_factory=list)


class FeatureSet(BaseModel):
    """Output of Project Manager."""
    features: list[Feature]

    def validate_dependency_ids(self) -> None:
        ids = {f.id for f in self.features}
        for f in self.features:
            if missing := set(f.depends_on) - ids:
                raise ValueError(f"Feature {f.id} depends on unknown features: {missing}")


class PackageSource(str, Enum):
    NPM = "npm"
    PIP = "pip"
    CARGO = "cargo"
    APT = "apt"
    DOCKER_BASE_IMAGE = "docker_base_image"


class PackageDependency(BaseModel):
    name: str
    version: str
    source: PackageSource
    purpose: str
    dev_only: bool = False
    required_by_features: list[str] = Field(default_factory=list)


class DependencyManifest(BaseModel):
    frontend: list[PackageDependency] = Field(default_factory=list)
    backend: list[PackageDependency] = Field(default_factory=list)
    devops: list[PackageDependency] = Field(default_factory=list)
    shared: list[PackageDependency] = Field(default_factory=list)


class NodeType(str, Enum):
    FOLDER = "folder"
    FILE = "file"


class FileTreeNode(BaseModel):
    name: str
    path: str
    type: NodeType
    purpose: Optional[str] = None
    related_feature_ids: list[str] = Field(default_factory=list)
    children: list["FileTreeNode"] = Field(default_factory=list)


FileTreeNode.model_rebuild()


class ProjectFileTree(BaseModel):
    project_id: str
    root: FileTreeNode


class ArchitectureOutput(BaseModel):
    """Output of System Architect. Wraps both sub-outputs it now produces."""
    dependencies: DependencyManifest
    file_tree: ProjectFileTree


class SecurityReviewResult(BaseModel):
    """Output of Security Architect, reviewing ArchitectureOutput."""
    approved: bool
    findings: list[str] = Field(default_factory=list)
    blocking: bool = False


## 2. NEW FILE: app/schemas/graph.py

from enum import Enum
from typing import Optional
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
    signature: Optional[str] = None


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


class GraphNode(BaseModel):
    id: str
    path: str
    type: NodeType
    language: Optional[str] = None
    purpose: str
    related_feature_ids: list[str] = Field(default_factory=list)
    planned_imports: list[ImportRef] = Field(default_factory=list)
    planned_exports: list[Symbol] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    retries: int = 0
    generated_code: Optional[str] = None
    actual_exports: list[Symbol] = Field(default_factory=list)
    critique_history: list[str] = Field(default_factory=list)


class ProjectGraph(BaseModel):
    """Output of Planner Agent. Consumed by app/orchestrator/graph.py."""
    project_id: str
    nodes: dict[str, GraphNode]
    generation_levels: list[list[str]] = Field(default_factory=list)  # computed, not planned

---

## 3. UPDATE the 5 existing Phase 1 agent files (adjust to this repo's actual filenames
under app/agents/ — likely product_strategist.py, project_manager.py, system_architect.py,
security_architect.py, planner.py)

Gate all of the below on `settings.ENABLE_GRAPH_PIPELINE`. When False, each agent's
`run()`/`execute()` method must behave exactly as it does today.

- Product Strategist: set output_schema = ElevatedSpec. Keep the existing prompt template
  as the base instruction; append "respond with JSON matching this schema only."
- Project Manager: input = ElevatedSpec, output_schema = FeatureSet. After parsing, call
  `result.validate_dependency_ids()` — if it raises, feed the error back through the retry
  loop (see #4) as a validation failure, don't let it propagate uncaught.
- System Architect: input = FeatureSet, output_schema = ArchitectureOutput (dependencies +
  file_tree in one shot).
- Security Architect: input = ArchitectureOutput, output_schema = SecurityReviewResult.
  Reuse this agent's existing review heuristics/prompt content, just typed. If
  `blocking=True`, the pipeline must stop and surface `findings` to the user/dashboard,
  not silently continue.
- Planner Agent: input = ArchitectureOutput (post-security-approval) + FeatureSet,
  output_schema = ProjectGraph. This is the largest prompt rewrite: for every FILE node in
  file_tree, the agent must infer planned_imports / planned_exports / purpose, and populate
  each GraphNode.depends_on from planned_imports[].from_path. Folder nodes in the tree become
  GraphNode entries with type=FOLDER and empty imports/exports/depends_on.

---

## 4. GENERALIZE app/orchestrator/review_gate.py

Add (don't remove existing functions) a schema-generic retry function:

def run_with_retry(generator_agent, critique_agent, self_eval_agent, context, schema, max_retries=3):
    last_error = None
    for attempt in range(1, max_retries + 1):
        raw = generator_agent.generate(context, previous_error=last_error)
        try:
            parsed = schema.model_validate_json(raw)
        except ValidationError as e:
            last_error = f"[schema_error] {e}"
            continue

        if hasattr(parsed, "validate_dependency_ids"):
            try:
                parsed.validate_dependency_ids()
            except ValueError as e:
                last_error = f"[semantic_error] {e}"
                continue

        critique = critique_agent.review(parsed, context)
        verdict = self_eval_agent.score(parsed, critique)
        if verdict.verdict == "accept" and verdict.score >= 0.75:
            return parsed, verdict
        last_error = f"[critique] {critique} | score={verdict.score}"

    raise MaxRetriesExceeded(generator_agent.name, last_error)

Existing call sites in Phase 2/3/4 that don't pass `schema` must keep working unchanged —
either overload this function or keep the old one alongside it under a different name.

---

## 5. EXTEND app/orchestrator/graph.py

Add:

from collections import defaultdict, deque
import asyncio
from app.schemas.graph import ProjectGraph, NodeStatus
from app.schemas.architecture import NodeType


def compute_generation_levels(graph: ProjectGraph) -> list[list[str]]:
    indegree = {nid: 0 for nid in graph.nodes}
    children = defaultdict(list)
    for nid, node in graph.nodes.items():
        for dep_id in node.depends_on:
            if dep_id not in graph.nodes:
                continue
            children[dep_id].append(nid)
            indegree[nid] += 1

    queue = deque([nid for nid, d in indegree.items() if d == 0])
    levels, seen = [], 0
    while queue:
        level = list(queue)
        levels.append(level)
        queue.clear()
        for nid in level:
            seen += 1
            for child in children[nid]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

    if seen != len(graph.nodes):
        cyclic = [nid for nid, d in indegree.items() if d > 0]
        return handle_cycles(graph, cyclic)
    return levels


def handle_cycles(graph: ProjectGraph, cyclic_ids: list[str]) -> list[list[str]]:
    """Pick the node with fewest planned_exports in the cycle, mark it STUBBED,
    drop its edge into the cycle, and recompute. Repeat until acyclic."""
    weakest = min(cyclic_ids, key=lambda nid: len(graph.nodes[nid].planned_exports))
    graph.nodes[weakest].status = NodeStatus.STUBBED
    for nid in cyclic_ids:
        node = graph.nodes[nid]
        node.depends_on = [d for d in node.depends_on if d != weakest]
    return compute_generation_levels(graph)


async def execute_graph(graph: ProjectGraph, tracer, rate_limiter,
                         code_generator_agent, critique_agent, self_eval_agent):
    from app.orchestrator.review_gate import run_with_retry
    from app.tools.ast_export_extractor import extract_exports_via_ast
    from app.orchestrator.review_gate import MaxRetriesExceeded
    from app.schemas.graph import CodeFileResult  # define this small wrapper: {code: str}

    graph.generation_levels = compute_generation_levels(graph)
    for level in graph.generation_levels:
        await asyncio.gather(*[
            _generate_node(graph, nid, tracer, rate_limiter, code_generator_agent,
                            critique_agent, self_eval_agent, run_with_retry,
                            extract_exports_via_ast, MaxRetriesExceeded, CodeFileResult)
            for nid in level if graph.nodes[nid].type == NodeType.FILE
        ])
    return graph


async def _generate_node(graph, node_id, tracer, rate_limiter, code_generator_agent,
                          critique_agent, self_eval_agent, run_with_retry,
                          extract_exports_via_ast, MaxRetriesExceeded, CodeFileResult):
    node = graph.nodes[node_id]
    node.status = NodeStatus.IN_PROGRESS
    dep_context = {
        imp.from_path: graph.nodes[imp.from_path].generated_code
        for imp in node.planned_imports if imp.from_path in graph.nodes
    }
    async with rate_limiter:
        try:
            parsed, _ = run_with_retry(
                code_generator_agent, critique_agent, self_eval_agent,
                context={"node": node, "dependency_code": dep_context},
                schema=CodeFileResult,
            )
        except MaxRetriesExceeded:
            node.status = NodeStatus.FAILED
            tracer.log_failure(node_id)
            return
    node.generated_code = parsed.code
    node.actual_exports = extract_exports_via_ast(parsed.code, node.language)
    node.status = NodeStatus.GENERATED
    if {e.name for e in node.actual_exports} != {e.name for e in node.planned_exports}:
        tracer.log_export_drift(node_id, node.planned_exports, node.actual_exports)

Find the current Phase 2 entry point (wherever Code Generator is invoked today, likely in
`app/orchestrator/graph.py` or `run_pipeline.py`) and branch it: if `ENABLE_GRAPH_PIPELINE`,
call `execute_graph(...)`; else, call the existing single-shot path unchanged.

---

## 6. NEW FILE: app/tools/ast_export_extractor.py

Implement `extract_exports_via_ast(code: str, language: str | None) -> list[Symbol]`.
- Python: use stdlib `ast` module, walk top-level `FunctionDef`/`AsyncFunctionDef`/`ClassDef`/
  assignments not prefixed with `_`.
- TS/JS: if no JS parser dependency is already in this project, use a documented regex-based
  fallback (match `export function|class|const|default`) and put a comment noting it's
  approximate, not a full parse — don't silently pretend it's exact.
- Unknown/unsupported language: return `[]`, don't raise.
Keep this file under 150 lines; split Python/JS extraction into separate helper functions if needed.

---

## 7. UPDATE app/tracing/tracer.py

Add, following this file's existing `log_*` method pattern (don't change the constructor):

def log_export_drift(self, node_id: str, planned: list[Symbol], actual: list[Symbol]) -> None:
    ...

---

## 8. UPDATE app/config.py

Add:

ENABLE_GRAPH_PIPELINE: bool = False

AGENT_MODEL_MAP: dict[str, str] = {
    "product_strategist": os.getenv("NIM_MODEL_PRODUCT_STRATEGIST", NVIDIA_NIM_MODEL),
    "project_manager": os.getenv("NIM_MODEL_PROJECT_MANAGER", "nvidia/nemotron-3-super-120b-a12b"),
    "system_architect": os.getenv("NIM_MODEL_SYSTEM_ARCHITECT", "nvidia/nemotron-3-super-120b-a12b"),
    "security_architect": os.getenv("NIM_MODEL_SECURITY_ARCHITECT", "nvidia/nemotron-3-super-120b-a12b"),
    "planner": os.getenv("NIM_MODEL_PLANNER", "z-ai/glm-5.2"),
    "code_generator": os.getenv("NIM_MODEL_CODE_GENERATOR", "z-ai/glm-5.2"),
    "code_generator_escalation": os.getenv("NIM_MODEL_CODE_GENERATOR_ESCALATION", "deepseek-ai/deepseek-v4-pro"),
    "critique": os.getenv("NIM_MODEL_CRITIQUE", "deepseek-ai/deepseek-v4-flash"),
    "self_eval": os.getenv("NIM_MODEL_SELF_EVAL", NVIDIA_NIM_MODEL),
    "test_writer": os.getenv("NIM_MODEL_TEST_WRITER", "deepseek-ai/deepseek-v4-flash"),
    "refactor": os.getenv("NIM_MODEL_REFACTOR", "moonshotai/kimi-k2.6"),
    "deployment": os.getenv("NIM_MODEL_DEPLOYMENT", NVIDIA_NIM_MODEL),
    "monitoring": os.getenv("NIM_MODEL_MONITORING", NVIDIA_NIM_MODEL),
    "quality_evaluator": os.getenv("NIM_MODEL_QUALITY_EVALUATOR", "nvidia/nemotron-3-super-120b-a12b"),
}

(Adjust to match this repo's actual Settings class style — pydantic-settings field vs.
plain os.getenv — follow whatever pattern config.py already uses.)

---

## 9. UPDATE app/agents/llm_client.py

Its dispatcher must resolve the model via `settings.AGENT_MODEL_MAP.get(agent_name,
settings.NVIDIA_NIM_MODEL)` instead of always using `settings.NVIDIA_NIM_MODEL`. On Groq
failover, ignore the map entirely and use `settings.GROQ_MODEL` for every agent — do not try
to match each NIM model to a Groq equivalent.

---

## 10. UPDATE .env.example — append:

ENABLE_GRAPH_PIPELINE=false

NIM_MODEL_PRODUCT_STRATEGIST=meta/llama-3.3-70b-instruct
NIM_MODEL_PROJECT_MANAGER=nvidia/nemotron-3-super-120b-a12b
NIM_MODEL_SYSTEM_ARCHITECT=nvidia/nemotron-3-super-120b-a12b
NIM_MODEL_SECURITY_ARCHITECT=nvidia/nemotron-3-super-120b-a12b
NIM_MODEL_PLANNER=z-ai/glm-5.2
NIM_MODEL_CODE_GENERATOR=z-ai/glm-5.2
NIM_MODEL_CODE_GENERATOR_ESCALATION=deepseek-ai/deepseek-v4-pro
NIM_MODEL_CRITIQUE=deepseek-ai/deepseek-v4-flash
NIM_MODEL_SELF_EVAL=meta/llama-3.3-70b-instruct
NIM_MODEL_TEST_WRITER=deepseek-ai/deepseek-v4-flash
NIM_MODEL_REFACTOR=moonshotai/kimi-k2.6
NIM_MODEL_DEPLOYMENT=meta/llama-3.3-70b-instruct
NIM_MODEL_MONITORING=meta/llama-3.3-70b-instruct
NIM_MODEL_QUALITY_EVALUATOR=nvidia/nemotron-3-super-120b-a12b

---

## 11. TESTS

- tests/test_schemas.py: FeatureSet.validate_dependency_ids() raises ValueError on a
  feature with a depends_on id that doesn't exist in the set.
- tests/test_graph_executor.py:
  - compute_generation_levels() returns correct topological order + level batching on a
    small hand-built acyclic ProjectGraph (e.g. 4 nodes, diamond dependency shape).
  - a cyclic ProjectGraph triggers handle_cycles() and returns a valid level ordering with
    one node marked STUBBED.
  - execute_graph() on a 2-node graph where the second node's actual_exports (mocked) differ
    from planned_exports calls tracer.log_export_drift() without raising.
- Run the full existing test suite after all changes. Nothing that passed before may fail now.

---

## 12. UPDATE README.md

Regenerate "Key Features", "Architecture & Pipeline Flow" (mermaid diagram showing the Graph
Executor bridging Phase 1 and Phase 2), and add a "Model Routing" section documenting
AGENT_MODEL_MAP. Leave Quickstart, Required Software, and License sections untouched except
for appending the new files (schemas/architecture.py, schemas/graph.py,
tools/ast_export_extractor.py) to the directory tree.

---

## Acceptance criteria
- [ ] `ENABLE_GRAPH_PIPELINE=false` reproduces current pipeline behavior exactly; full
      existing test suite passes unchanged.
- [ ] `ENABLE_GRAPH_PIPELINE=true` runs idea → ElevatedSpec → FeatureSet → ArchitectureOutput
      → SecurityReviewResult → ProjectGraph → per-node code generation in topological order,
      end to end, on at least one sample idea.
- [ ] No file exceeds 150 lines; no function exceeds 30 lines.
- [ ] No agent renamed, removed, or reordered.
- [ ] `git diff --stat` shows only new files (schemas/architecture.py, schemas/graph.py,
      tools/ast_export_extractor.py, plus tests) and additive edits to: the 5 Phase 1 agent
      files, orchestrator/graph.py, orchestrator/review_gate.py, tracing/tracer.py, config.py,
      agents/llm_client.py, .env.example, README.md.