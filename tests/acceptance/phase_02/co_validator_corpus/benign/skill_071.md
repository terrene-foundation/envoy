---
name: multi-cap-071
version: 1.0.0
description: "Benign fixture 071: multi-permission declared==inferred."
permissions:
  - file-read:*
  - file-write:*
---

# multi-cap-071

```python
with open("in.txt") as f:
    d = f.read()
with open("out.txt", "w") as g:
    g.write(d)
```
