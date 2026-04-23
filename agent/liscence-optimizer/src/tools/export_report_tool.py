"""
Export Report Tool - Exports analysis reports as markdown files.

This tool allows the agent to save generated reports, analysis results,
or any text content to markdown files for user download.
"""

import json
from pathlib import Path
from datetime import datetime
from agenticai.tools import tool_registry


@tool_registry.register(
    name="export_report",
    description="Export text content (reports, analysis, documentation) as a markdown file. Use this to save final reports, analysis results, or any generated content to a .md file that users can download.",
    tags=["export", "markdown", "save", "file"],
    requires_context=False,
)
def export_report(content: str, filename: str | None = None, title: str | None = None) -> str:
    """
    Export content as a markdown file.
    
    Args:
        content: The text content to export (markdown formatted)
        filename: Optional filename (default: auto-generated with timestamp)
        title: Optional title to add at the top of the file
    
    Returns:
        JSON string with:
        - success: True if saved successfully
        - filename: The saved filename
        - path: Full path to the saved file
        - size: File size in bytes
        
    Example:
        >>> export_report(content="# My Report\n\nContent here", filename="analysis_report.md", title="Analysis Report")
        >>> # Saves the report to analysis_report.md
    """
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Generate filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"report_{timestamp}.md"
        
        # Ensure .md extension
        if not filename.endswith('.md'):
            filename += '.md'
        
        # Prepare content
        output_content = ""
        if title:
            output_content = f"# {title}\n\n"
        output_content += content
        
        # Save to current directory (where the agent runs)
        file_path = Path.cwd() / filename
        file_path.write_text(output_content, encoding='utf-8')
        
        file_size = file_path.stat().st_size
        
        result = {
            "success": True,
            "filename": filename,
            "path": str(file_path),
            "size_bytes": file_size,
            "size_human": f"{file_size / 1024:.1f} KB",
            "message": f"Report successfully exported to {filename}"
        }
        
        logger.info(f"Exported report to {file_path} ({result['size_human']})")
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to export report: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": f"Failed to export report: {str(e)}"
        })
