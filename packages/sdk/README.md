# CScode SDK

Python SDK for programmatic access to CScode AI coding assistant.

## Usage

```python
from cscode_sdk import create_cscode, CScodeClient

# Create a local instance
app = create_cscode()
print(app.version)

# Connect to a remote server
client = CScodeClient(base_url="http://localhost:8000", api_key="sk-...")
sessions = await client.list_sessions()
```
