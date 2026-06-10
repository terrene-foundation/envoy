---
name: http-getter-063
version: 1.0.0
description: "Benign fixture 063: http-get declared==inferred."
permissions:
  - http-get:api.example.com
---

# http-getter-063

```python
import httpx
httpx.get("https://api.example.com/data")
```
