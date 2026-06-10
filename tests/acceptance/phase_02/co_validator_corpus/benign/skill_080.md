---
name: over-declarer-080
version: 1.0.0
description: "Benign fixture 080: over-declaration (declared superset)."
permissions:
  - file-read:*
  - http-post:api.example.com
---

# over-declarer-080

```python
with open("only-read.txt") as f:
    data = f.read()
```
