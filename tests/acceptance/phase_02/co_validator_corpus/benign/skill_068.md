---
name: over-declarer-068
version: 1.0.0
description: "Benign fixture 068: over-declaration (declared superset)."
permissions:
  - file-read:*
  - http-post:api.example.com
---

# over-declarer-068

```python
with open("only-read.txt") as f:
    data = f.read()
```
