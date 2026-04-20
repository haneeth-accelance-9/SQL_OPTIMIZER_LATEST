"""
This agent creates executive summary or the results that are obtained by applying usecases on the data

This module provides an A2A (Agent-to-Agent) protocol server,
enabling integration with other AI agents and systems.
"""

import os

# Import AgenticAI SDK
from agenticai.a2a import A2AFactory

# Import local tools
try:
    from . import tools  # noqa: F401
except ImportError:
    import tools  # noqa: F401


def main():
    """
    Start the A2A server.

    All configuration is loaded from the config file specified by the CONFIG_PATH
    environment variable, or defaults to config.yaml if not set.
    
    Supports debugpy for VS Code debugging when DEBUGPY_ENABLE=true environment variable is set.
    """
    # Check if debugger should be enabled
    if os.environ.get("DEBUGPY_ENABLE", "").lower() == "true":
        try:
            import debugpy
            
            debugpy.listen(("0.0.0.0", 5678))  # nosec B104 - Intentional for debugger access
            print("Debugger enabled - listening on port 5678")
            
            # Only wait for client if DEBUGPY_WAIT is set (Docker mode)
            if os.environ.get("DEBUGPY_WAIT", "").lower() == "true":
                print("   Waiting for VS Code debugger to attach...")
                debugpy.wait_for_client()
                print("Debugger attached!")
            else:
                print("   Server starting - attach debugger when ready")
        except ImportError:
            print("WARNING: debugpy not installed - continuing without debugger")
        except Exception as e:
            print(f"WARNING: Failed to start debugger: {e}")
    
    factory = A2AFactory()
    server = factory.create_server()
    server.run()


if __name__ == "__main__":
    main()