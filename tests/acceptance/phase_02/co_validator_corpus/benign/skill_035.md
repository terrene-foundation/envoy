---
name: multi-cap-035
version: 1.0.0
description: "Benign fixture 035: multi-permission declared==inferred."
permissions:
  - file-read:*
  - file-write:*
---

# multi-cap-035

```python
with open("in.txt") as f:
    d = f.read()
with open("out.txt", "w") as g:
    g.write(d)
```
