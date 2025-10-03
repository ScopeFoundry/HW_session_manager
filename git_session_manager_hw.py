import subprocess
import datetime
from pathlib import Path
from ScopeFoundry import HardwareComponent


class GitSessionManagerHW(HardwareComponent):
    """
    Hardware component for managing experimental sessions using git branches.
    
    Features:
    - Automatic branch creation for new experimental sessions
    - Session state tracking and git operations
    - Commit initial state when starting sessions
    """
    
    name = "git_session_manager"
    
    def setup(self):
        """Set up the git session manager settings and operations"""
        
        # Session identification settings
        self.session_name = self.settings.New(
            "session_name", 
            dtype=str, 
            initial="", 
            description="Name for the current experimental session"
        )
        
        self.session_prefix = self.settings.New(
            "session_prefix",
            dtype=str,
            initial="exp",
            description="Prefix for experimental session branch names"
        )
        
        # Session state tracking
        self.current_branch = self.settings.New(
            "current_branch",
            dtype=str,
            initial="",
            ro=True,
            description="Current git branch"
        )
        
        self.current_commit_hash = self.settings.New(
            "current_commit_hash",
            dtype=str,
            initial="",
            ro=True,
            description="Current git commit hash"
        )
        
        self.session_active = self.settings.New(
            "session_active",
            dtype=bool,
            initial=False,
            ro=True,
            description="Whether an experimental session is currently active"
        )
        
        self.session_branch = self.settings.New(
            "session_branch",
            dtype=str,
            initial="",
            ro=True,
            description="Git branch for the current session"
        )
        
        self.parent_branch = self.settings.New(
            "parent_branch",
            dtype=str,
            initial="",
            ro=True,
            description="Branch that the session was created from"
        )
        
        # Repository info
        self.repo_path = self.settings.New(
            "repo_path",
            dtype=str,
            initial=str(Path.cwd()),
            description="Path to the git repository"
        )
        
        self.has_uncommitted_changes = self.settings.New(
            "has_uncommitted_changes",
            dtype=bool,
            initial=False,
            ro=True,
            description="Whether there are uncommitted changes"
        )
        
        self.session_ended = self.settings.New(
            "session_ended",
            dtype=bool,
            initial=False,
            ro=True,
            description="Whether the current session has been explicitly ended"
        )
        
        # Git operations
        self.add_operation("Start Session", self.start_experimental_session)
        self.add_operation("End Session", self.end_experimental_session)
        self.add_operation("Commit Changes", self.commit_session_changes)
        self.add_operation("Return to Parent Branch", self.return_to_parent_branch)
        self.add_operation("Refresh Status", self.refresh_git_status)
        
    def connect(self):
        """Connect to git and initialize status"""
        self.refresh_git_status()
        
    def disconnect(self):
        """Disconnect from git session manager"""
        # TODO should the session end on disconnect?
        pass
        
    def _run_git_command(self, cmd, check=True, silent_fail=False, input_text=None):
        """Execute a git command and return the result"""
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path.val,
                capture_output=True,
                text=True,
                check=check,
                input=input_text
            )
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.CalledProcessError as e:
            if not silent_fail:
                self.log.error(f"Git command failed: {' '.join(cmd)}")
                self.log.error(f"Error: {e.stderr}")
                self.log.error(f"Return code: {e.returncode}")
            raise
            
    def refresh_git_status(self):
        """Refresh git status information"""
        try:
            # Get current branch
            stdout, stderr, returncode = self._run_git_command(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
            )
            self.current_branch.update_value(stdout)
            
            # Get current commit hash
            stdout, stderr, returncode = self._run_git_command(
                ['git', 'rev-parse', 'HEAD']
            )
            self.current_commit_hash.update_value(stdout)
            
            # Check for uncommitted changes
            stdout, stderr, returncode = self._run_git_command(
                ['git', 'status', '--porcelain']
            )
            has_changes = bool(stdout.strip())
            self.has_uncommitted_changes.update_value(has_changes)
            
            # Update session status
            current_branch = self.current_branch.val
            is_session_branch = current_branch.startswith(f"{self.session_prefix.val}-")
            
            # Session is active only if on session branch AND not explicitly ended
            session_active = is_session_branch and not self.session_ended.val
            self.session_active.update_value(session_active)
            
            if is_session_branch:
                self.session_branch.update_value(current_branch)
            else:
                self.session_branch.update_value("")
                # Reset session_ended flag when not on a session branch
                self.session_ended.update_value(False)
                
            self.log.info(f"Git status refreshed - Branch: {current_branch}, Changes: {has_changes}")
            
        except Exception as e:
            self.log.error(f"Failed to refresh git status: {e}")
            
    def generate_session_branch_name(self, session_name=None):
        """Generate a branch name for the experimental session"""
        if session_name is None:
            session_name = self.session_name.val
            
        if not session_name:
            # Generate default name with timestamp
            timestamp = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
            session_name = f"session-{timestamp}"
            
        # Clean session name for git branch
        clean_name = session_name.replace(" ", "-").replace("_", "-")
        clean_name = "".join(c for c in clean_name if c.isalnum() or c in "-.")
        
        branch_name = f"{self.session_prefix.val}-{clean_name}"
        return branch_name
        
    def start_experimental_session(self):
        """Start a new experimental session by creating and switching to a new git branch"""
        try:
            if self.session_active.val:
                raise ValueError("A session is already active. End the current session first.")
                
            # Record the current branch as the parent branch
            parent_branch = self.current_branch.val
            self.parent_branch.update_value(parent_branch)
                
            # Generate branch name
            branch_name = self.generate_session_branch_name()
            
            # Check if branch already exists
            try:
                self._run_git_command(['git', 'rev-parse', '--verify', branch_name], silent_fail=True)
                raise ValueError(f"Branch {branch_name} already exists")
            except subprocess.CalledProcessError:
                # Branch doesn't exist, which is what we want
                pass
                
            # Create and switch to new branch
            self._run_git_command(['git', 'checkout', '-b', branch_name])
            
            # Reset session_ended flag for new session
            self.session_ended.update_value(False)
            
            # Commit initial state
            self.commit_initial_session_state(branch_name)
            
            # Create tag for session start
            self.create_session_tag(branch_name)
            
            # Update status
            self.refresh_git_status()
            
            self.log.info(f"Started experimental session on branch: {branch_name}")
            
        except Exception as e:
            self.log.error(f"Failed to start experimental session: {e}")
            raise
            
    def commit_initial_session_state(self, branch_name):
        """Commit the initial state when starting a session"""
        try:
            # Check if there are any changes to commit first
            stdout, stderr, returncode = self._run_git_command(
                ['git', 'status', '--porcelain'], 
                check=False
            )
            
            if not stdout.strip():
                # No changes to commit, create an empty commit to mark session start
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                session_name = self.session_name.val or "unnamed session"
                
                commit_message = f"""Start experimental session: {session_name}

Session Details:
- Session name: {session_name}
- Branch: {branch_name}
- Started: {timestamp}
- ScopeFoundry Git Session Manager

Generated with ScopeFoundry Git Session Manager"""

                self._run_git_command(['git', 'commit', '--allow-empty', '-F', '-'], input_text=commit_message)
                self.log.info(f"Created empty commit to mark session start for {session_name}")
            else:
                # There are changes, add and commit them
                self._run_git_command(['git', 'add', '-A'])
                
                # Check again if there are staged changes after add
                stdout_after_add, _, _ = self._run_git_command(
                    ['git', 'diff', '--cached', '--quiet'],
                    check=False
                )
                
                # git diff --cached --quiet returns 1 if there are staged changes, 0 if none
                stdout_status, _, returncode_status = self._run_git_command(
                    ['git', 'status', '--porcelain'],
                    check=False
                )
                
                if not stdout_status.strip():
                    # Nothing was actually staged (e.g., all files ignored)
                    self.log.info("No changes to commit after git add (files may be ignored)")
                    return
                
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                session_name = self.session_name.val or "unnamed session"
                
                commit_message = f"""Initial state for experimental session: {session_name}

Session Details:
- Session name: {session_name}
- Branch: {branch_name}
- Started: {timestamp}
- ScopeFoundry Git Session Manager

Generated with ScopeFoundry Git Session Manager"""

                self._run_git_command(['git', 'commit', '-F', '-'], input_text=commit_message)
                self.log.info(f"Committed initial session state for {session_name}")
            
        except subprocess.CalledProcessError as e:
            self.log.error(f"Git commit failed with return code {e.returncode}")
            self.log.error(f"Git stderr: {e.stderr}")
            self.log.error(f"Git stdout: {e.stdout}")
            if "nothing to commit" in str(e.stderr):
                self.log.info("No changes to commit for initial session state")
            else:
                self.log.error(f"Failed to commit initial session state: {e}")
                raise
                
    def create_session_tag(self, branch_name):
        """Create a git tag to mark the session start"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            session_name = self.session_name.val or "session"
            
            # Clean session name for tag (similar to branch name cleaning)
            clean_name = session_name.replace(" ", "-").replace("_", "-")
            clean_name = "".join(c for c in clean_name if c.isalnum() or c in "-.")
            
            tag_name = f"session-start-{clean_name}-{timestamp}"
            
            # Create tag message
            tag_message = f"""Session start tag for: {session_name}

Tag Details:
- Session name: {session_name}
- Branch: {branch_name}
- Created: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- ScopeFoundry Git Session Manager

Generated with ScopeFoundry Git Session Manager"""

            # Create annotated tag
            self._run_git_command(['git', 'tag', '-a', tag_name, '-m', tag_message])
            
            self.log.info(f"Created session tag: {tag_name}")
            
        except Exception as e:
            self.log.error(f"Failed to create session tag: {e}")
            # Don't raise the error as tagging failure shouldn't stop session creation
                
    def end_experimental_session(self):
        """End the current experimental session"""
        try:
            if not self.session_active.val:
                raise ValueError("No active session to end")
                
            current_session_branch = self.session_branch.val
            
            # Commit any final changes
            if self.has_uncommitted_changes.val:
                self.commit_session_changes(final=True)
                
            # Mark session as ended (but stay on the session branch)
            self.session_ended.update_value(True)
            
            # Update status (session will be marked inactive due to session_ended flag)
            self.refresh_git_status()
            
            self.log.info(f"Ended experimental session on branch: {current_session_branch} (branch preserved)")
            
        except Exception as e:
            self.log.error(f"Failed to end experimental session: {e}")
            raise
            
    def return_to_parent_branch(self):
        """Return to the parent branch that the session was created from"""
        try:
            if not self.parent_branch.val:
                raise ValueError("No parent branch recorded. Cannot return to parent branch.")
                
            parent_branch = self.parent_branch.val
            
            # Check if there are uncommitted changes
            if self.has_uncommitted_changes.val:
                raise ValueError(f"There are uncommitted changes. Please commit or stash them before switching branches.")
            
            # Switch to parent branch
            self._run_git_command(['git', 'checkout', parent_branch])
            
            # Update status
            self.refresh_git_status()
            
            self.log.info(f"Returned to parent branch: {parent_branch}")
            
        except Exception as e:
            self.log.error(f"Failed to return to parent branch: {e}")
            raise
            
    def commit_session_changes(self, final=False):
        """Commit changes during the experimental session"""
        try:
            if not self.session_active.val:
                raise ValueError("No active session to commit changes for")
                
            if not self.has_uncommitted_changes.val:
                self.log.info("No changes to commit")
                return
                
            # Add all changes
            self._run_git_command(['git', 'add', '-A'])
            
            # Create commit message
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            session_name = self.session_name.val or "experimental session"
            
            if final:
                commit_message = f"""Final commit for experimental session: {session_name}

Session completed at: {timestamp}
Branch: {self.session_branch.val}

Generated with ScopeFoundry Git Session Manager"""
            else:
                commit_message = f"""Progress commit for experimental session: {session_name}

Updated at: {timestamp}
Branch: {self.session_branch.val}

Generated with ScopeFoundry Git Session Manager"""

            self._run_git_command(['git', 'commit', '-F', '-'], input_text=commit_message)
            
            # Update status
            self.refresh_git_status()
            
            commit_type = "Final" if final else "Progress"
            self.log.info(f"{commit_type} commit completed for session: {session_name}")
            
        except subprocess.CalledProcessError as e:
            if "nothing to commit" in e.stderr:
                self.log.info("No changes to commit")
            else:
                raise
        except Exception as e:
            self.log.error(f"Failed to commit session changes: {e}")
            raise