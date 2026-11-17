# tools/__init__.py
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    fn: Callable

TOOL_REGISTRY: dict[str, Tool] = {}
