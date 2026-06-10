---
name: over-declarer-032
version: 1.0.0
description: "Benign fixture 032: over-declaration (declared superset)."
permissions:
  - file-read:*
  - http-post:api.example.com
---

# over-declarer-032

```python
with open("only-read.txt") as f:
    data = f.read()
```
