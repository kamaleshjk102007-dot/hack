import json, os
from config.settings import MEMORY_FILE, MEMORY_MAX

class Memory:
    def __init__(self):
        self._file = MEMORY_FILE
        self._data = self._load()

    def _load(self):
        if os.path.exists(self._file):
            try:
                with open(self._file, encoding="utf-8") as handle:
                    return json.load(handle)
            except: pass
        return []

    def save(self, role: str, content: str, *, origin=None,
             verification_status=None, sources=None):
        """Save conversation context with explicit factual provenance.

        User-provided content is never promoted to verified knowledge. Source
        URLs are stored only when they came from the retrieval pipeline.
        """
        item = {"role": role, "content": content}
        if verification_status == "VERIFIED" and not sources:
            verification_status = "UNVERIFIED"
        if origin:
            item["origin"] = origin
        if verification_status:
            item["verification_status"] = verification_status
        if sources:
            item["sources"] = list(dict.fromkeys(sources))
        self._data.append(item)
        if len(self._data) > MEMORY_MAX:
            self._data = self._data[-MEMORY_MAX:]
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except: pass

    def get_history(self):  return list(self._data)
    def clear(self):
        self._data = []
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except: pass
    def __len__(self):      return len(self._data)
