---
name: bash-runner-004
version: 1.0.0
description: "Benign fixture 004: bash declared==inferred."
permissions:
  - bash:*
---

# bash-runner-004

```python
import subprocess
subprocess.run(["ls", "-la"])
```
