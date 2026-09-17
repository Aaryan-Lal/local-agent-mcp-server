"""Shared helpers for turning extracted (subject, relation, object) triples into
safe RDF/SPARQL against GraphDB, and back again."""
import re

RESOURCE_NS = "http://local-kb.example/resource/"
RELATION_NS = "http://local-kb.example/relation/"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"


def slugify(text: str) -> str:
    """Turn arbitrary entity text into a safe URI path segment."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "unknown"


def to_uri(namespace: str, text: str) -> str:
    """Build a bracketed SPARQL URI reference, e.g. <http://.../resource/eve>."""
    return f"<{namespace}{slugify(text)}>"


def escape_sparql_literal(value: str) -> str:
    """Escape a string for safe use inside a double-quoted SPARQL string literal.

    This is the SPARQL-injection guardrail: query text is never concatenated
    into a SPARQL string unescaped.
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
