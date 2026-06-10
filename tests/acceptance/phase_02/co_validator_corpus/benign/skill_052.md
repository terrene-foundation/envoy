---
name: bash-runner-052
version: 1.0.0
description: "Benign fixture 052: bash declared==inferred."
permissions:
  - bash:*
---

# bash-runner-052

```python
import subprocess
subprocess.run(["ls", "-la"])
```
