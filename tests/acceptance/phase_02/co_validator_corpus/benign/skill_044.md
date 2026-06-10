---
name: over-declarer-044
version: 1.0.0
description: "Benign fixture 044: over-declaration (declared superset)."
permissions:
  - file-read:*
  - http-post:api.example.com
---

# over-declarer-044

```python
with open("only-read.txt") as f:
    data = f.read()
```
