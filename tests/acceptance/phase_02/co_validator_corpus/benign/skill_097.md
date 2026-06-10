---
name: file-writer-097
version: 1.0.0
description: "Benign fixture 097: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-097

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
