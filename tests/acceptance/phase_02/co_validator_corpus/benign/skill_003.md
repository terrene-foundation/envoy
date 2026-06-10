---
name: http-getter-003
version: 1.0.0
description: "Benign fixture 003: http-get declared==inferred."
permissions:
  - http-get:api.example.com
---

# http-getter-003

```python
import httpx
httpx.get("https://api.example.com/data")
```
