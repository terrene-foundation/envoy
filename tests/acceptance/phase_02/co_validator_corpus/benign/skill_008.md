---
name: over-declarer-008
version: 1.0.0
description: "Benign fixture 008: over-declaration (declared superset)."
permissions:
  - file-read:*
  - http-post:api.example.com
---

# over-declarer-008

```python
with open("only-read.txt") as f:
    data = f.read()
```
