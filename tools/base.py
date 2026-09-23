"""
tools/base.py - Base infrastructure for the controlled tool execution subsystem.
Provides schema definitions, argument validation, execution sandboxing, and execution tracing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """Specification for a tool input argument."""
    name: str
    type_name: str  # "string", "integer", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolResult:
    """Standardized output structure for all tool executions."""
    tool_name: str
    success: bool
    data: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """Abstract Base Class for all Research Agent Tools."""

    def __init__(self, name: str, description: str, parameters: Optional[List[ToolParameter]] = None):
        self.name = name
        self.description = description
        self.parameters = parameters or []

    def get_schema(self) -> Dict[str, Any]:
        """Returns JSON schema representation of the tool."""
        props = {}
        required = []
        for p in self.parameters:
            props[p.name] = {
                "type": p.type_name,
                "description": p.description,
            }
            if p.default is not None:
                props[p.name]["default"] = p.default
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        }

    def validate_args(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Validates input arguments against tool parameter specifications."""
        sanitized = {}
        for p in self.parameters:
            if p.name in kwargs:
                val = kwargs[p.name]
                # Basic type coercion/validation
                if p.type_name == "string" and not isinstance(val, str):
                    val = str(val)
                elif p.type_name == "integer" and not isinstance(val, int):
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        raise ValueError(f"Parameter '{p.name}' must be an integer, got {type(val).__name__}")
                elif p.type_name == "number" and not isinstance(val, (int, float)):
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        raise ValueError(f"Parameter '{p.name}' must be a number, got {type(val).__name__}")
                elif p.type_name == "boolean" and not isinstance(val, bool):
                    if isinstance(val, str):
                        val = val.lower() in ("true", "1", "yes")
                    else:
                        val = bool(val)
                sanitized[p.name] = val
            elif p.required:
                if p.default is not None:
                    sanitized[p.name] = p.default
                else:
                    raise ValueError(f"Missing required argument: '{p.name}' for tool '{self.name}'")
            else:
                sanitized[p.name] = p.default
        return sanitized

    def execute(self, **kwargs) -> ToolResult:
        """Executes the tool with timing, validation, and error sandboxing."""
        t0 = time.perf_counter()
        try:
            validated_kwargs = self.validate_args(kwargs)
            result_data = self._run(**validated_kwargs)
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=result_data,
                execution_time_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.warning(f"Tool execution failed for '{self.name}': {e}", exc_info=False)
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error=str(e),
                execution_time_ms=duration_ms,
            )

    @abstractmethod
    def _run(self, **kwargs) -> Any:
        """Actual tool business logic implemented by subclasses."""
        pass


class ToolRegistry:
    """Central registry and dispatcher for all agent tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registers a tool instance."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieves a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """Returns list of registered tool names."""
        return list(self._tools.keys())

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """Returns schemas for all registered tools."""
        return [tool.get_schema() for tool in self._tools.values()]

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Executes a registered tool by name."""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=f"Tool '{tool_name}' not found in registry. Available: {self.list_tools()}",
            )
        return tool.execute(**kwargs)
