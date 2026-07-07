"""Validated schemas for code generation output."""


from pydantic import BaseModel, Field, field_validator


class CodeGenerationOutput(BaseModel):
    """Validated code generation output with strict filename and content checks."""

    files: dict[str, str] = Field(
        description="Map of filepath to file content. Keys must include file extensions."
    )

    @field_validator('files')
    @classmethod
    def validate_filenames(cls, v: dict[str, str]) -> dict[str, str]:
        """Ensure all keys are valid filenames with extensions."""
        invalid = []

        for filename, content in v.items():
            # Must have extension (except dotfiles like .gitignore)
            if '.' not in filename and not filename.startswith('.'):
                invalid.append(f"'{filename}' missing extension")
                continue

            # Content must be string
            if not isinstance(content, str):
                invalid.append(f"'{filename}' content must be string, got {type(content).__name__}")
                continue

            # Content must not be empty or too short
            if len(content.strip()) < 10:
                invalid.append(f"'{filename}' content too short ({len(content)} chars)")

        if invalid:
            raise ValueError(f"Invalid files: {'; '.join(invalid[:5])}")

        return v

    @field_validator('files')
    @classmethod
    def check_minimum_files(cls, v: dict[str, str]) -> dict[str, str]:
        """Ensure at least one valid file is generated."""
        if len(v) == 0:
            raise ValueError("No files generated - output is empty")

        return v

    def has_html(self) -> bool:
        """Check if output contains HTML files."""
        return any(f.endswith('.html') for f in self.files.keys())

    def has_package_json(self) -> bool:
        """Check if output contains package.json."""
        return 'package.json' in self.files or any('package.json' in f for f in self.files.keys())

    def get_file_count_by_type(self) -> dict[str, int]:
        """Get count of files by extension."""
        counts = {}
        for filename in self.files.keys():
            ext = filename.split('.')[-1] if '.' in filename else 'no_extension'
            counts[ext] = counts.get(ext, 0) + 1
        return counts
