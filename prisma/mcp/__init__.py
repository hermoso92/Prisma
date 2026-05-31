"""Servidor MCP de Prisma.

Expone tu base de conocimiento como herramientas vía el **Model Context Protocol**,
para que un cliente (Claude Desktop, Claude Code…) consulte tu contexto real.

Implementación sin dependencias: JSON-RPC 2.0 sobre stdio (mensajes JSON
delimitados por saltos de línea, que es el transporte estándar de MCP). Todo
local; el servidor solo lee tu base de datos.
"""

from prisma.mcp.server import McpServer, PROTOCOL_VERSION

__all__ = ["McpServer", "PROTOCOL_VERSION"]
