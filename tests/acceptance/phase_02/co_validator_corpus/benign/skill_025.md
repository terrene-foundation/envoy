---
name: file-writer-025
version: 1.0.0
description: "Benign fixture 025: file-write declared==inferred."
permissions:
  - file-write:*
---

# file-writer-025

```python
with open("out.txt", "w") as f:
    f.write("hi")
```
