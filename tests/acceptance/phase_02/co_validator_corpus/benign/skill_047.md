---
name: multi-cap-047
version: 1.0.0
description: "Benign fixture 047: multi-permission declared==inferred."
permissions:
  - file-read:*
  - file-write:*
---

# multi-cap-047

```python
with open("in.txt") as f:
    d = f.read()
with open("out.txt", "w") as g:
    g.write(d)
```
