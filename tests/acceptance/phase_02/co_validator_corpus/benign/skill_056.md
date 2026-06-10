---
name: over-declarer-056
version: 1.0.0
description: "Benign fixture 056: over-declaration (declared superset)."
permissions:
  - file-read:*
  - http-post:api.example.com
---

# over-declarer-056

```python
with open("only-read.txt") as f:
    data = f.read()
```
