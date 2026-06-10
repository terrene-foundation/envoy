---
name: file-writer-037
version: 1.0.0
description: "Benign fixture 037: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-037

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
