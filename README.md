# ScopeFoundry Git Session Manager

A ScopeFoundry hardware component that provides experimental session management using git branches. This component automatically creates git branches for experimental sessions and tracks session state through git operations.

## Features

- **Automatic Branch Creation**: Creates a new git branch when starting an experimental session
- **Session State Tracking**: Monitors current branch, session status, and uncommitted changes
- **Initial State Commit**: Automatically commits the initial state when starting a session
- **Session Tagging**: Creates annotated git tags at session start for easy reference
- **Session Management**: Easy start/end operations with proper git workflow
- **Progress Tracking**: Commit changes during the session with descriptive messages

## Installation

1. Place the `session_manager` directory in your ScopeFoundryHW collection
2. Import and use the `GitSessionManagerHW` component in your ScopeFoundry application

## Usage

### Basic Integration

```python
from ScopeFoundry import BaseMicroscopeApp
from ScopeFoundryHW.session_manager.git_session_manager_hw import GitSessionManagerHW

class MyApp(BaseMicroscopeApp):
    def setup(self):
        # Add the git session manager
        self.add_hardware(GitSessionManagerHW)
```

### Session Workflow

1. **Configure Session Name** (optional):
   - Set the `session_name` setting to give your session a meaningful name
   - If not set, a timestamp-based name will be generated automatically

2. **Start Session**:
   - Click "Start Session" button or call `start_experimental_session()`
   - Creates a new branch with format: `{prefix}-{session_name}`
   - Commits initial state with session metadata
   - Creates an annotated git tag to mark session start

3. **Work on Experiment**:
   - Make changes to your files as needed
   - Use "Commit Changes" to save progress during the session
   - Monitor session status through the UI

4. **End Session**:
   - Click "End Session" button or call `end_experimental_session()`
   - Commits final changes and returns to main/master branch

### Settings

- **session_name**: Name for the current experimental session
- **session_prefix**: Prefix for branch names (default: "exp")
- **repo_path**: Path to the git repository (default: current working directory)
- **current_branch**: Current git branch (read-only)
- **session_active**: Whether a session is currently active (read-only)
- **session_branch**: Git branch for current session (read-only)
- **has_uncommitted_changes**: Whether there are uncommitted changes (read-only)

### Operations

- **Start Session**: Begin a new experimental session
- **End Session**: End the current session and return to main branch
- **Commit Changes**: Commit current changes with session metadata
- **Refresh Status**: Update git status information

## Branch Naming Convention

Branches are created with the following format:
```
{session_prefix}-{clean_session_name}
```

Examples:
- `exp-laser-calibration`
- `exp-sample-analysis-001`
- `exp-session-240926-143022` (auto-generated)

## Session Tags

Session start tags are created with the following format:
```
session-start-{clean_session_name}-{timestamp}
```

Examples:
- `session-start-laser-calibration-20240926-143022`
- `session-start-sample-analysis-001-20240926-150030`
- `session-start-test-with-tags-20250926-165340`

## Commit Messages

The component generates descriptive commit messages:

**Initial session commit:**
```
Initial state for experimental session: laser calibration

Session Details:
- Session name: laser calibration
- Branch: exp-laser-calibration
- Started: 2024-09-26 14:30:22
- ScopeFoundry Git Session Manager

Generated with ScopeFoundry Git Session Manager
```

**Progress commits:**
```
Progress commit for experimental session: laser calibration

Updated at: 2024-09-26 15:45:10
Branch: exp-laser-calibration

Generated with ScopeFoundry Git Session Manager
```

## Requirements

- Git repository initialized in the working directory
- Git command-line tools available
- ScopeFoundry framework
- Python 3.6+

## Error Handling

The component handles common git scenarios:
- Repository not initialized
- Branch already exists
- No changes to commit
- Network issues (for remote operations)

## Testing

Run the test application:

```bash
cd ScopeFoundryHW/session_manager
python test_app.py
```

This will open a ScopeFoundry application with the Git Session Manager component loaded.

## Integration Examples

### With Measurement Classes

```python
class MyMeasurement(Measurement):
    def pre_run(self):
        # Ensure we're in a session before running
        git_hw = self.app.hardware['git_session_manager']
        if not git_hw.session_active.val:
            git_hw.start_experimental_session()
    
    def post_run(self):
        # Commit results after measurement
        git_hw = self.app.hardware['git_session_manager']
        git_hw.commit_session_changes()
```

### Automatic Session Management

```python
# Start session at app startup
def start_experiment_session(self):
    git_hw = self.app.hardware['git_session_manager']
    git_hw.session_name.update_value("automated-experiment")
    git_hw.start_experimental_session()

# End session at app shutdown
def cleanup_session(self):
    git_hw = self.app.hardware['git_session_manager']
    if git_hw.session_active.val:
        git_hw.end_experimental_session()
```

## Working with Session Tags

Session tags provide easy reference points for experimental sessions:

```bash
# List all session start tags
git tag -l "session-start-*"

# Show tag details and commit
git show session-start-laser-calibration-20240926-143022

# Checkout to a specific session start point
git checkout session-start-laser-calibration-20240926-143022

# Create a new branch from a session tag
git checkout -b analysis-branch session-start-laser-calibration-20240926-143022

# Compare current state with session start
git diff session-start-laser-calibration-20240926-143022
```

## Future Enhancements

Potential features for future versions:
- Remote repository push/pull operations
- Session metadata export to H5 files
- Integration with ScopeFoundry's existing git_funcs module
- Session templating and configuration
- Multi-repository support
- Session archiving and cleanup tools
- End-of-session tags for complete session lifecycle tracking