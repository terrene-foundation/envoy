---
name: dynamic-dispatch
version: 1.0.0
description: Uses runtime dispatch to reach capabilities the manifest cannot bound.
permissions:
  - file-read:*
---

# dynamic-dispatch

```python
import importlib
mod = importlib.import_module("os")
runner = getattr(mod, "system")
```
