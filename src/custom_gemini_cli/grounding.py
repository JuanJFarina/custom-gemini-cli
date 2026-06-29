from __future__ import annotations

from typing import Any


def print_sources(response: Any) -> None:
    sources = list(extract_sources(response))
    if not sources:
        return

    print("\nSources:")
    for index, source in enumerate(sources, start=1):
        title = source["title"]
        uri = source["uri"]
        print(f"{index}. {title} - {uri}")


def extract_sources(response: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()

    for candidate in _get(response, "candidates") or []:
        metadata = _get(candidate, "grounding_metadata") or _get(
            candidate,
            "groundingMetadata",
        )
        for chunk in _get(metadata, "grounding_chunks") or _get(
            metadata,
            "groundingChunks",
        ) or []:
            web = _get(chunk, "web")
            uri = _get(web, "uri")
            if not uri or uri in seen:
                continue

            seen.add(uri)
            sources.append(
                {
                    "title": _get(web, "title") or uri,
                    "uri": uri,
                }
            )

    return sources


def _get(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
