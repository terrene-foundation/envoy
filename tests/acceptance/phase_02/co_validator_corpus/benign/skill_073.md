---
name: file-writer-073
version: 1.0.0
description: "Benign fixture 073: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-073

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
