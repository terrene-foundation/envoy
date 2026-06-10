---
name: file-writer-001
version: 1.0.0
description: "Benign fixture 001: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-001

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
