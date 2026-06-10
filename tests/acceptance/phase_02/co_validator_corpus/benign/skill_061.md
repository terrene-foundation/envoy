---
name: file-writer-061
version: 1.0.0
description: "Benign fixture 061: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-061

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
