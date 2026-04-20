"""
Read File Content Tool - Reads text and markdown files from message attachments.

This tool allows the agent to read the actual content of text-based files
that are attached to messages, rather than treating them as data to analyze.
"""

import json
import base64
from pathlib import Path
from agenticai.tools import tool_registry


@tool_registry.register(
    name="read_file_content",
    description="Read the full text content of attached text, markdown, or document files. Use this to read use case documents, requirements, or any text-based files. Returns the complete file content as text.",
    tags=["files", "text", "markdown", "read"],
    requires_context=False,
)
def read_file_content(filename: str) -> str:
    """
    Read and return the full text content of an attached file.
    
    This tool is designed for reading text-based files like:
    - Markdown (.md) files
    - Text (.txt) files
    - Documents with text content
    
    Args:
        filename: Name of the file to read (e.g., 'sample_use_case.md')
    
    Returns:
        JSON string with:
        - content: The full text content of the file
        - filename: Name of the file
        - size: Size in bytes
        - encoding: Detected encoding
        
    Example:
        >>> result = read_file_content("requirements.md")
        >>> # Returns the full markdown content
    
    **IMPORTANT**: Use this tool instead of upload_dataframe for text/markdown files.
    """
    from agenticai.a2a.context import get_current_session_id
    from agenticai.a2a.executors.base_executor import get_file_context
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        session_id = get_current_session_id()
        if not session_id:
            return json.dumps({"error": "No active session"})
        
        files = get_file_context(session_id)
        
        if not files:
            return json.dumps({"error": "No files attached to this message"})
        
        # Find the requested file
        target_file = None
        for file_info in files:
            if file_info["name"] == filename or file_info["name"].endswith(filename):
                target_file = file_info
                break
        
        if not target_file:
            available = [f["name"] for f in files]
            return json.dumps({
                "error": f"File '{filename}' not found",
                "available_files": available,
                "suggestion": f"Available files: {', '.join(available)}"
            })
        
        # Get the file bytes
        file_bytes = target_file["bytes"]
        
        # Try to decode as text with various encodings
        encodings_to_try = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        content = None
        used_encoding = None
        
        for encoding in encodings_to_try:
            try:
                content = file_bytes.decode(encoding)
                used_encoding = encoding
                logger.info(f"Successfully decoded '{filename}' using {encoding}")
                break
            except (UnicodeDecodeError, AttributeError):
                continue
        
        if content is None:
            return json.dumps({
                "error": f"Could not decode file '{filename}' as text",
                "suggestion": "File may be binary or use an unsupported encoding"
            })
        
        # Return the content
        result = {
            "success": True,
            "filename": target_file["name"],
            "content": content,
            "size_bytes": len(file_bytes),
            "size_human": f"{len(file_bytes) / 1024:.1f} KB",
            "encoding": used_encoding,
            "lines": len(content.splitlines())
        }
        
        logger.info(f"Read file '{filename}': {len(content)} characters, {result['lines']} lines")
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to read file content: {e}", exc_info=True)
        return json.dumps({"error": f"Failed to read file: {str(e)}"})
