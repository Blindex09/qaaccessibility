import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

class Registry:
    def __init__(self):
        self.tools: dict[str, dict[str, Any]] = {}
        self.toolsets: dict[str, list[str]] = {}

    def register(
        self,
        name: str,
        toolset: str,
        schema: dict[str, Any],
        handler: Callable[..., Any],
        is_async: bool = False,
        emoji: str = "",
        requires_approval: bool = False,
        needs_clarify_callback: bool = False,
    ) -> None:
        """Register a tool.

        ``needs_clarify_callback`` marks tools whose handler takes a second
        argument: the clarify callback that asks the user a question and blocks
        until the answer arrives. ``run_local_tool`` supplies it.
        """
        self.tools[name] = {
            "schema": schema,
            "handler": handler,
            "is_async": is_async,
            "emoji": emoji,
            "requires_approval": requires_approval,
            "needs_clarify_callback": needs_clarify_callback,
        }
        if toolset not in self.toolsets:
            self.toolsets[toolset] = []
        if name not in self.toolsets[toolset]:
            self.toolsets[toolset].append(name)
        logger.info("[Registry] Tool '%s' registered in toolset '%s'", name, toolset)

    def get_tool_names_for_toolset(self, toolset: str) -> list[str]:
        return self.toolsets.get(toolset, [])

registry = Registry()
