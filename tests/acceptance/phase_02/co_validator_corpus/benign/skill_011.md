---
name: multi-cap-011
version: 1.0.0
description: "Benign fixture 011: multi-permission declared==inferred."
permissions:
  - file-read:*
  - file-write:*
---

# multi-cap-011

```python
with open("in.txt") as f:
    d = f.read()
with open("out.txt", "w") as g:
    g.write(d)
```
