---
name: bash-runner-016
version: 1.0.0
description: "Benign fixture 016: bash declared==inferred."
permissions:
  - bash:*
---

# bash-runner-016

```python
import subprocess
subprocess.run(["ls", "-la"])
```
