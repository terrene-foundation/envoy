---
name: file-writer-085
version: 1.0.0
description: "Benign fixture 085: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-085

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
