"""Envelope template resolver — Phase 01 local-only stub.

Per `specs/envelope-library.md` § "Trust tiers": the Foundation Library
registry endpoint is Phase 02 per `specs/foundation-ops.md`. Phase 01 ships
local-disk template resolution only.

Per shard 4 § 3 step 3, the compiler invokes the resolver to fold template
constraints into per-dimension `imported_constraints[]` with `authored=false`.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from envoy.envelope.errors import TemplateResolutionError


@dataclass(frozen=True, slots=True)
class TemplateRef:
    """Reference to an envelope template.

    Phase 01 supports `local:<path>` references only. Phase 02 adds
    `foundation-verified:<id>@<version>` and `community:<author>:<id>`.
    """

    uri: str  # e.g. "local:templates/family-budget.json"


@dataclass(frozen=True, slots=True)
class EnvelopeTemplate:
    """Resolved template content.

    `template_hash` is sha256 over the canonical-bytes form of `content`.
    Carried verbatim into `imported_constraints[].template_hash` so the
    consumer can verify the template hasn't drifted since import.
    """

    ref: TemplateRef
    content: dict[str, Any]
    template_hash: str
    template_origin: str = field(default="local")


class EnvelopeTemplateResolver(Protocol):
    """Protocol for template resolution.

    Phase 01 ships LocalTemplateResolver; Phase 02 adds
    FoundationVerifiedTemplateResolver + CommunityTemplateResolver.
    """

    def resolve(self, ref: TemplateRef) -> EnvelopeTemplate: ...


class LocalTemplateResolver:
    """Local-disk template resolver. Phase 01 only.

    Reads JSON files from a configured root directory; refuses any URI scheme
    other than `local:`. No publisher signature validation in Phase 01 (that
    surface is Phase 02 per Foundation Library registry spec).
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()

    def resolve(self, ref: TemplateRef) -> EnvelopeTemplate:
        if not ref.uri.startswith("local:"):
            raise TemplateResolutionError(
                f"LocalTemplateResolver only supports 'local:' URIs (got scheme of {ref.uri!r})",
            )
        rel = ref.uri[len("local:") :]
        path = (self._root / rel).resolve()
        if not str(path).startswith(str(self._root)):
            raise TemplateResolutionError(
                "template path traversal refused",
            )
        if not path.is_file():
            raise TemplateResolutionError(
                f"template not found at local path (uri={ref.uri!r})",
            )
        try:
            content: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TemplateResolutionError(
                f"template parse failed (uri={ref.uri!r}): {type(exc).__name__}",
            ) from exc
        if not isinstance(content, dict):
            raise TemplateResolutionError("template must be a JSON object")
        # Hash matches canonical_bytes pipeline so cross-SDK byte-identity holds
        # even on imported-constraint provenance trail.
        canonical = json.dumps(
            _nfc_normalize(content),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        template_hash = hashlib.sha256(canonical).hexdigest()
        return EnvelopeTemplate(
            ref=ref,
            content=content,
            template_hash=template_hash,
            template_origin="local",
        )


def _nfc_normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {_nfc_normalize(k): _nfc_normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_nfc_normalize(v) for v in value]
    return value
