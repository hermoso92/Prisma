"""Embeddings: representación vectorial del contenido para búsqueda semántica.

Capa enchufable, igual que el análisis:

- ``ollama`` (recomendado): embeddings locales y gratuitos con un modelo de Ollama
  (por defecto ``nomic-embed-text``). 100% offline, nada sale del equipo.
- ``hashing``: respaldo determinista sin dependencias ni servicios. No es
  semántico de verdad (es léxico), pero permite usar y probar la búsqueda
  vectorial sin Ollama.
"""

from prisma.embeddings.base import Embedder, get_embedder, EMBEDDERS
from prisma.embeddings.hashing import HashingEmbedder
from prisma.embeddings.ollama import OllamaEmbedder

__all__ = ["Embedder", "HashingEmbedder", "OllamaEmbedder", "get_embedder", "EMBEDDERS"]
