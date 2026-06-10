---
name: file-reader-072
version: 1.0.0
description: "Benign fixture 072: file-read declared==inferred."
permissions:
  - file-read:*
---

# file-reader-072

```python
with open("data.txt") as f:
    contents = f.read()
```
