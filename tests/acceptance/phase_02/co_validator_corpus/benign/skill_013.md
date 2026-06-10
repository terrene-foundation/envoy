---
name: file-writer-013
version: 1.0.0
description: "Benign fixture 013: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-013

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
