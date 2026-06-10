---
name: http-getter-051
version: 1.0.0
description: "Benign fixture 051: http-get declared==inferred."
permissions:
  - http-get:api.example.com
---

# http-getter-051

```python
import httpx
httpx.get("https://api.example.com/data")
```
