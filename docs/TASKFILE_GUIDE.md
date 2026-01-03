# Taskfile Usage Guide

This project uses [Task](https://taskfile.dev/) (go-task) as a task runner to simplify common operations. This guide explains how to use the available tasks and best practices.

## Installation

### Using mise (Recommended)
```bash
mise install task=latest
```

### Manual Installation
Visit [https://taskfile.dev/installation/](https://taskfile.dev/installation/) for installation instructions for your platform.

## Available Tasks

### Setup and Initialization
- `task setup` - Complete project setup (virtual environment, dependencies, database initialization)
- `task install-deps` - Install dependencies only
- `task update-deps` - Update dependencies
- `task init-db` - Initialize the database

### Running the Application
- `task run` - Run the main OpenRouter tracker script
- `task run -- --help` - Show script help (pass arguments after `--`)

### Testing
- `task test` - Run all tests
- `task test-unit` - Run unit tests only
- `task test-format` - Run table format tests
- `task test-discord` - Run Discord notification tests

### Code Quality
- `task lint` - Check code with linters (ruff)
- `task lint-fix` - Fix code issues automatically

### Maintenance
- `task clean` - Clean temporary files and virtual environment
- `task clean-logs` - Clean log files
- `task clean-db` - Remove database files
- `task reset` - Complete cleanup (clean + logs + db)
- `task status` - Show project status

### Utilities
- `task check-config` - Verify config.yaml exists
- `task cron-setup` - Show cron setup instructions
- `task help` - List all available tasks

## Best Practices

### 1. Initial Setup
Always start with:
```bash
task setup
```

### 2. Daily Usage
For regular execution:
```bash
task run
```

### 3. Development Workflow
```bash
# Before committing code
task lint-fix
task test

# After pulling updates
task update-deps
```

### 4. Cron Automation
For automatic execution, use Task in cron:
```bash
# Add to crontab with: crontab -e
0 6 * * * cd /path/to/openrouter-tracker && task run
0 18 * * * cd /path/to/openrouter-tracker && task run
```

### 5. Environment Variables
Task respects environment variables. You can use with dotenvx:
```bash
dotenvx exec -- task run
```

## Taskfile Structure

The Taskfile.yml is organized as follows:

- **Variables**: Project-wide variables like Python path and pip path
- **Dependencies**: Tasks that other tasks depend on (using `deps`)
- **Commands**: Shell commands to execute for each task
- **Descriptions**: Human-readable descriptions for `task --list`

## Advanced Usage

### Passing Arguments
You can pass arguments to tasks that run scripts:
```bash
task run -- --help
```

### Running Multiple Tasks
```bash
task lint test run
```

### Dry Run
To see what a task would do without executing:
```bash
task --dry setup
```

### Verbose Output
For detailed output:
```bash
task --verbose run
```

## Troubleshooting

### Task Not Found
If `task` command is not found:
1. Verify installation: `which task`
2. Install via mise: `mise install task=latest`
3. Or install manually from [https://taskfile.dev/installation/](https://taskfile.dev/installation/)

### Virtual Environment Issues
If Python dependencies are not found:
```bash
task clean
task setup
```

### Permission Issues
If you encounter permission issues:
```bash
chmod +x Taskfile.yml  # Though this is usually not needed
```

## Migration from setup.sh

The Taskfile provides all functionality from the old setup.sh script plus additional features:

| Old (setup.sh) | New (Task) | Notes |
|----------------|------------|-------|
| `./setup.sh` | `task setup` | Equivalent functionality |
| Manual steps | Single commands | Much simpler workflow |
| Limited options | Rich task set | More capabilities |

## Benefits of Using Task

1. **Consistency**: Same commands across different environments
2. **Discoverability**: `task help` shows all available commands
3. **Dependency Management**: Tasks can depend on other tasks
4. **Cross-Platform**: Works on Linux, macOS, and Windows
5. **Maintainability**: Centralized task definitions in Taskfile.yml
6. **Extensibility**: Easy to add new tasks as project grows

## Configuration

The Taskfile is configured in `Taskfile.yml` and uses these project variables:
- `PROJECT_NAME`: openrouter-tracker
- `PYTHON_PATH`: ./venv/bin/python3
- `PIP_PATH`: ./venv/bin/pip

These can be overridden by setting environment variables or modifying the Taskfile.yml directly.