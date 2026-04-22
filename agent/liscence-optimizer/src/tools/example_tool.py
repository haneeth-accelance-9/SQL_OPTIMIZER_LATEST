"""
Example Tool - Template for agent tools.

Customize this tool or create new ones based on your agent's requirements.
"""

from agenticai.tools import tool_registry


@tool_registry.register("example_tool")
class ExampleTool:
    """Example tool demonstrating the tool interface."""

    name = "example_tool"
    description = "An example tool that greets the user"

    def execute(self, name: str = "User") -> str:
        """
        Greet the user by name.

        Args:
            name: Name to greet

        Returns:
            Greeting message
        """
        return f"Hello, {name}! This is an example tool from LiscenceOptimizer."