"""Local multi-format resume importer."""

SUPPORTED_EXTENSIONS = {
    ".doc", ".docm", ".docx", ".dotx", ".htm", ".html", ".mht", ".mhtml",
    ".pdf", ".ppt", ".pptx", ".txt", ".wps", ".xls", ".xlsb", ".xlsx",
    ".xml", ".jpg", ".jpeg", ".png", ".bmp", ".eml"
}

from .universal_schema_parser import UniversalSchemaParser
from .gemini_html_schema_parser import GeminiHtmlSchemaParser

__all__ = ["SUPPORTED_EXTENSIONS", "UniversalSchemaParser", "GeminiHtmlSchemaParser"]
