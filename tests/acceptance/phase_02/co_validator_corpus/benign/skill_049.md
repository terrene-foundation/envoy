---
name: file-writer-049
version: 1.0.0
description: "Benign fixture 049: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-049

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
