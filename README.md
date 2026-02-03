# OpenAI Agents Tools

Powerful file, shell, and web tools for [OpenAI Agents SDK](https://github.com/openai/openai-agents-python).

## Features

- **File Tools**: Read, write, edit files with glob patterns and grep search
- **Shell Tool**: Execute shell commands with approval mechanism
- **Web Tools**: Search the web and fetch URL content
- **Utility Tools**: Think (reasoning) and Todo list management
- **Approval System**: Built-in approval mechanism for dangerous operations

## Installation

```bash
pip install openai-agents-tools
```

With optional dependencies:

```bash
# All features
pip install openai-agents-tools[all]

# Web tools only
pip install openai-agents-tools[web]

# Grep with ripgrep
pip install openai-agents-tools[grep]

# Media file support (image size detection)
pip install openai-agents-tools[media]
```

## Quick Start

```python
import asyncio
from pathlib import Path
from agents import Agent, Runner
from openai_agents_tools import KimiToolContext, get_all_tools

async def main():
    # Create context
    context = KimiToolContext(
        work_dir=Path.cwd(),
        yolo_mode=True,  # Skip all approval prompts
    )

    # Create agent with tools
    agent = Agent(
        name="FileAssistant",
        instructions="You are a helpful file assistant.",
        tools=get_all_tools(),
    )

    # Run
    result = await Runner.run(agent, "Read README.md", context=context)
    print(result.final_output)

asyncio.run(main())
```

## Available Tools

### File Tools
| Tool | Description | Requires Approval |
|------|-------------|-------------------|
| `read_file` | Read text files with line numbers | No |
| `write_file` | Write/append content to files | **Yes** |
| `str_replace_file` | Find and replace in files | **Yes** |
| `glob_tool` | Find files by glob patterns | No |
| `grep` | Search file contents with regex | No |
| `read_media_file` | Read image/video files | No |

### Shell Tool
| Tool | Description | Requires Approval |
|------|-------------|-------------------|
| `shell` | Execute shell commands | **Yes** |

### Web Tools
| Tool | Description | Requires Approval |
|------|-------------|-------------------|
| `search_web` | Search the internet | No |
| `fetch_url` | Fetch and extract web page content | No |

### Utility Tools
| Tool | Description | Requires Approval |
|------|-------------|-------------------|
| `think` | Log thoughts for complex reasoning | No |
| `set_todo_list` | Manage todo list for multi-step tasks | No |

## Approval Mechanism

Tools that modify files or execute commands require approval. You can control this via:

### 1. YOLO Mode (skip all approvals)

```python
context = KimiToolContext(
    work_dir=Path.cwd(),
    yolo_mode=True,
)
```

### 2. Auto-approve specific actions

```python
context = KimiToolContext(
    work_dir=Path.cwd(),
    auto_approved_actions={"edit file", "run command"},
)
```

### 3. Custom approval callback

```python
async def my_approval_callback(tool_name: str, action: str, description: str) -> bool:
    print(f"{tool_name} wants to {action}: {description}")
    response = input("Approve? (y/n): ")
    return response.lower() == 'y'

context = KimiToolContext(
    work_dir=Path.cwd(),
    approval_callback=my_approval_callback,
)
```

## Web Tools Configuration

Web tools require service configuration:

```python
from openai_agents_tools import KimiToolContext, WebServiceConfig

context = KimiToolContext(
    work_dir=Path.cwd(),
    search_service=WebServiceConfig(
        base_url="https://api.example.com/search",
        api_key="your-api-key",
    ),
    fetch_service=WebServiceConfig(
        base_url="https://api.example.com/fetch",
        api_key="your-api-key",
    ),
)
```

## Tool Selection Helpers

```python
from openai_agents_tools import (
    get_all_tools,      # All tools
    get_safe_tools,     # Only tools that don't require approval
    get_file_tools,     # File operation tools
    get_web_tools,      # Web tools
)
```

## License

MIT License
