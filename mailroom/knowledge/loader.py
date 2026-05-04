"""Per-tenant knowledge loader. Reads markdown from tenants/<name>/, caches with mtime invalidation."""
import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class KnowledgeBundle:
    kb_text: str
    voice_text: str
    version: str  # short hash, stable across loads of identical content


class KnowledgeLoader:
    """Per-process cache. Reloads when any contributing file's mtime changes."""

    def __init__(self, tenants_root: Path):
        self._tenants_root = tenants_root
        self._cache: dict[str, tuple[float, KnowledgeBundle]] = {}
        self._lock = Lock()

    def load(self, tenant_name: str) -> KnowledgeBundle:
        tenant_dir = self._tenants_root / tenant_name
        if not tenant_dir.exists():
            raise FileNotFoundError(f"No tenant directory: {tenant_dir}")

        kb_dir = tenant_dir / "knowledge"
        voice_path = tenant_dir / "voice.md"
        kb_files = sorted(kb_dir.glob("*.md")) if kb_dir.exists() else []

        latest_mtime = max(
            [p.stat().st_mtime for p in kb_files] + [voice_path.stat().st_mtime if voice_path.exists() else 0.0]
        )

        with self._lock:
            cached = self._cache.get(tenant_name)
            if cached and cached[0] == latest_mtime:
                return cached[1]

            kb_text = "\n\n".join(p.read_text() for p in kb_files)
            voice_text = voice_path.read_text() if voice_path.exists() else ""
            version = hashlib.sha256((kb_text + "\n\n" + voice_text).encode()).hexdigest()[:12]
            bundle = KnowledgeBundle(kb_text=kb_text, voice_text=voice_text, version=version)

            self._cache[tenant_name] = (latest_mtime, bundle)
            return bundle
