"""Pydantic schemas for Phase 1 Architecture contracts."""

from enum import Enum

from pydantic import BaseModel, Field


class TechStack(BaseModel):
    frontend: str | None = None
    backend: str | None = None
    database: str | None = None
    devops: str | None = None
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
        """Verify all dependency IDs exist in the feature set."""
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
    purpose: str | None = None
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
