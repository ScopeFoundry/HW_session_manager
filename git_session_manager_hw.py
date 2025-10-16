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
    SESSION_PREFIX = "session"
    
    def setup(self):
        """Set up the git session manager settings and operations"""
        
        # Session identification settings
        self.session_name = self.settings.New(
            "session_name", 
            dtype=str, 
            initial="", 
            description="Name for the current experimental session"
        )
        
        self.manage_submodules = self.settings.New(
            "manage_submodules",
            dtype=bool,
            initial=False,
            description="Whether to create session branches in submodules and track their changes"
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
        
        # self.session_ended = self.settings.New(
        #     "session_ended",
        #     dtype=bool,
        #     initial=False,
        #     ro=True,
        #     description="Whether the current session has been explicitly ended"
        # )
        
        # Git operations
        self.add_operation("Start Session", self.start_experimental_session)
        # self.add_operation("End Session", self.end_experimental_session)
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
            
    def get_submodules(self):
        """Get list of submodules in the repository"""
        try:
            stdout, _, _ = self._run_git_command(
                ['git', 'config', '--file', '.gitmodules', '--get-regexp', 'path'],
                check=False
            )
            
            if not stdout:
                return []
            
            submodules = []
            for line in stdout.splitlines():
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        submodule_path = parts[1]
                        submodules.append(submodule_path)
            
            return submodules
            
        except Exception as e:
            self.log.error(f"Failed to get submodules: {e}")
            return []
    
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
            cmd = ['git', 'status', '--porcelain']
            if not self.manage_submodules.val:
                cmd.append('--ignore-submodules')
            stdout, _, _ = self._run_git_command(cmd)
            has_changes = bool(stdout.strip())
            self.has_uncommitted_changes.update_value(has_changes)
            
            # Update session status
            current_branch = self.current_branch.val
            is_session_branch = current_branch.startswith(f"{self.SESSION_PREFIX}-")
            
            # Session is active if on a session branch
            session_active = is_session_branch
            self.session_active.update_value(session_active)
            
            if is_session_branch:
                self.session_branch.update_value(current_branch)
            else:
                self.session_branch.update_value("")
                
            self.log.info(f"Git status refreshed - Branch: {current_branch}, Changes: {has_changes}")
            
        except Exception as e:
            self.log.error(f"Failed to refresh git status: {e}")
            
    def generate_session_branch_name(self, session_name=None):
        """Generate a branch name for the experimental session"""
        if session_name is None:
            session_name = self.session_name.val
        
        # Always include timestamp
        timestamp = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
        
        if session_name:
            # Clean session name for git branch
            clean_name = session_name.replace(" ", "-").replace("_", "-")
            clean_name = "".join(c for c in clean_name if c.isalnum() or c in "-.")
            # Update the LQ with cleaned name
            self.session_name.update_value(clean_name)
            branch_name = f"{self.SESSION_PREFIX}-{timestamp}-{clean_name}"
        else:
            # No session name provided, just timestamp
            branch_name = f"{self.SESSION_PREFIX}-{timestamp}"
        
        return branch_name
        
    def start_experimental_session(self):
        """Start a new experimental session by creating and switching to a new git branch"""
        try:
            # If a session is already active, just record the current session branch as parent
            if self.session_active.val:
                self.log.info("A session is already active. Starting new session from current session branch.")
                
            # Record the current branch as the parent branch
            parent_branch = self.current_branch.val
            self.parent_branch.update_value(parent_branch)
                
            # Generate branch name
            branch_name = self.generate_session_branch_name()
            
            # Check if branch already exists and increment if needed
            original_branch_name = branch_name
            counter = 1
            while True:
                _, _, returncode = self._run_git_command(
                    ['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{branch_name}'],
                    check=False
                )
                if returncode == 0:
                    # Branch exists, try next number
                    branch_name = f"{original_branch_name}-{counter}"
                    counter += 1
                else:
                    # Branch doesn't exist, use this name
                    break
            
            # Update session_name if branch name was modified
            if branch_name != original_branch_name:
                session_name_from_branch = branch_name.replace(f"{self.SESSION_PREFIX}-", "", 1)
                self.session_name.update_value(session_name_from_branch)
                
            # Create and switch to new branch
            self._run_git_command(['git', 'checkout', '-b', branch_name])
            
            # Reset session_ended flag for new session (kept for backward compatibility)
            # self.session_ended.update_value(False)
            
            # Handle submodules if enabled
            if self.manage_submodules.val:
                self.start_session_in_submodules(branch_name, parent_branch)
            
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
            
    def start_session_in_submodules(self, branch_name, parent_branch):
        """Create session branches in all submodules, recording their parent branches in the commit message"""
        try:
            submodules = self.get_submodules()
            
            if not submodules:
                self.log.info("No submodules found")
                return
            
            submodule_parent_branches = {}
            
            for submodule_path in submodules:
                try:
                    submodule_full_path = Path(self.repo_path.val) / submodule_path
                    
                    self.log.info(f"Creating session branch in submodule: {submodule_path}")
                    
                    # Get current branch in submodule
                    result = subprocess.run(
                        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                        cwd=submodule_full_path,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    submodule_current_branch = result.stdout.strip()
                    submodule_parent_branches[submodule_path] = submodule_current_branch
                    
                    # Create and switch to new branch in submodule
                    subprocess.run(
                        ['git', 'checkout', '-b', branch_name],
                        cwd=submodule_full_path,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    
                    self.log.info(f"Created branch {branch_name} in submodule {submodule_path} (was on {submodule_current_branch})")
                    
                except subprocess.CalledProcessError as e:
                    self.log.warning(f"Failed to create session branch in submodule {submodule_path}: {e.stderr}")
                except Exception as e:
                    self.log.warning(f"Failed to process submodule {submodule_path}: {e}")
            
            # Store submodule parent branches in a file
            if submodule_parent_branches:
                parent_branches_file = Path(self.repo_path.val) / '.git' / 'session_submodule_parents.txt'
                with open(parent_branches_file, 'w') as f:
                    for path, branch in submodule_parent_branches.items():
                        f.write(f"{path}:{branch}\n")
                    
        except Exception as e:
            self.log.error(f"Failed to start session in submodules: {e}")
    
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
                
                commit_message = f"""Start experimental session: {branch_name}

Session Details:
- Branch: {branch_name}
- Started: {timestamp}
- ScopeFoundry Git Session Manager

Generated with ScopeFoundry Git Session Manager"""

                self._run_git_command(['git', 'commit', '--allow-empty', '-F', '-'], input_text=commit_message)
                self.log.info(f"Created empty commit to mark session start for {branch_name}")
            else:
                # There are changes, add and commit them
                self._run_git_command(['git', 'add', '-A'])
                
                # Check if there are actually staged changes after add
                _, _, returncode = self._run_git_command(
                    ['git', 'diff', '--cached', '--quiet'],
                    check=False
                )
                
                # git diff --cached --quiet returns 1 if there are staged changes, 0 if none
                if returncode == 0:
                    # Nothing was actually staged (e.g., all files ignored or submodule changes)
                    self.log.info("No changes to commit after git add (files may be ignored or only submodule changes)")
                    return
                
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                commit_message = f"""Initial state for experimental session: {branch_name}

Session Details:
- Branch: {branch_name}
- Started: {timestamp}
- ScopeFoundry Git Session Manager

Generated with ScopeFoundry Git Session Manager"""

                self._run_git_command(['git', 'commit', '-F', '-'], input_text=commit_message)
                self.log.info(f"Committed initial session state for {branch_name}")
            
        except subprocess.CalledProcessError as e:
            self.log.error(f"Git commit failed with return code {e.returncode}")
            self.log.error(f"Git stderr: {e.stderr}")
            self.log.error(f"Git stdout: {e.stdout}")
            if "nothing to commit" in str(e.stderr):
                self.log.info("No changes to commit for initial session state")
            else:
                self.log.error(f"Failed to commit initial session state: {e}")
                raise
                
    def create_session_tag(self, branch_name, tag_type="start"):
        """Create a git tag to mark the session start or end"""
        try:
            tag_name = f"{tag_type}-{branch_name}"
            
            # Create tag message
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tag_message = f"""Session {tag_type} tag for: {branch_name}

Tag Details:
- Branch: {branch_name}
- Created: {timestamp}
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
            
            # Create end tag
            # self.create_session_tag(current_session_branch, tag_type="end")
                
            # Mark session as ended (but stay on the session branch)
            # self.session_ended.update_value(True)
            
            # Update status (session will be marked inactive due to session_ended flag)
            self.refresh_git_status()
            
            self.log.info(f"Ended experimental session on branch: {current_session_branch} (branch preserved)")
            
        except Exception as e:
            self.log.error(f"Failed to end experimental session: {e}")
            raise
            
    def commit_submodule_changes(self, final=False):
        """Commit changes in all submodules"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            branch_name = self.session_branch.val
            
            # Create commit message
            if final:
                commit_message = f"""Final commit for experimental session: {branch_name}

Session completed at: {timestamp}

Generated with ScopeFoundry Git Session Manager"""
            else:
                commit_message = f"""Progress commit for experimental session: {branch_name}

Updated at: {timestamp}

Generated with ScopeFoundry Git Session Manager"""
            
            # Add all changes in all submodules
            self._run_git_command(['git', 'submodule', 'foreach', 'git add -A'])
            
            # Commit in all submodules
            self._run_git_command(['git', 'submodule', 'foreach', 'git', 'commit', '-F', '-'], input_text=commit_message, check=False)
            
            self.log.info("Committed changes in submodules")
                    
        except Exception as e:
            self.log.error(f"Failed to commit submodule changes: {e}")
    
    def return_to_parent_branch(self):
        """Return to the parent branch that the session was created from"""
        try:
            if not self.parent_branch.val:
                raise ValueError("No parent branch recorded. Cannot return to parent branch.")
                
            parent_branch = self.parent_branch.val
            
            # End the session if it's still active
            if self.session_active.val:
                self.log.info("Ending session before returning to parent branch")
                self.end_experimental_session()
            
            # Return submodules to their original branches if enabled
            if self.manage_submodules.val:
                self.return_submodules_to_parent_branch()
            
            # Switch to parent branch
            self._run_git_command(['git', 'checkout', parent_branch])
            
            # Update status
            self.refresh_git_status()
            
            self.log.info(f"Returned to parent branch: {parent_branch}")
            
        except Exception as e:
            self.log.error(f"Failed to return to parent branch: {e}")
            raise
            
    def return_submodules_to_parent_branch(self):
        """Return all submodules to their parent branches using stored branch information"""
        try:
            submodules = self.get_submodules()
            
            if not submodules:
                return
            
            # Read stored submodule parent branches
            parent_branches_file = Path(self.repo_path.val) / '.git' / 'session_submodule_parents.txt'
            submodule_parent_branches = {}
            
            if parent_branches_file.exists():
                with open(parent_branches_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if ':' in line:
                            path, branch = line.split(':', 1)
                            submodule_parent_branches[path] = branch
            
            for submodule_path in submodules:
                try:
                    submodule_full_path = Path(self.repo_path.val) / submodule_path
                    
                    # Check for uncommitted changes in submodule
                    result = subprocess.run(
                        ['git', 'status', '--porcelain'],
                        cwd=submodule_full_path,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    
                    if result.stdout.strip():
                        self.log.warning(f"Submodule {submodule_path} has uncommitted changes. Skipping checkout.")
                        continue
                    
                    # Get the stored parent branch for this submodule
                    parent_branch = submodule_parent_branches.get(submodule_path)
                    
                    if not parent_branch:
                        self.log.warning(f"No parent branch recorded for submodule {submodule_path}. Skipping checkout.")
                        continue
                    
                    self.log.info(f"Returning submodule {submodule_path} to parent branch {parent_branch}")
                    
                    subprocess.run(
                        ['git', 'checkout', parent_branch],
                        cwd=submodule_full_path,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    
                    self.log.info(f"Returned submodule {submodule_path} to branch {parent_branch}")
                    
                except subprocess.CalledProcessError as e:
                    self.log.warning(f"Failed to return submodule {submodule_path} to parent branch: {e.stderr}")
                except Exception as e:
                    self.log.warning(f"Failed to process submodule {submodule_path}: {e}")
                    
        except Exception as e:
            self.log.error(f"Failed to return submodules to parent branch: {e}")
            
    def commit_session_changes(self, final=False):
        """Commit changes during the experimental session"""
        try:
            if not self.session_active.val:
                raise ValueError("No active session to commit changes for")
                
            if not self.has_uncommitted_changes.val:
                self.log.info("No changes to commit")
                return
            
            # Commit changes in submodules first if enabled
            if self.manage_submodules.val:
                self.commit_submodule_changes(final)
                
            # Add all changes
            self._run_git_command(['git', 'add', '-A'])
            
            # Create commit message
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            branch_name = self.session_branch.val
            
            if final:
                commit_message = f"""Final commit for experimental session: {branch_name}

Session completed at: {timestamp}

Generated with ScopeFoundry Git Session Manager"""
            else:
                commit_message = f"""Progress commit for experimental session: {branch_name}

Updated at: {timestamp}

Generated with ScopeFoundry Git Session Manager"""

            self._run_git_command(['git', 'commit', '-F', '-'], input_text=commit_message)
            
            # Update status
            self.refresh_git_status()
            
            commit_type = "Final" if final else "Progress"
            self.log.info(f"{commit_type} commit completed for session: {branch_name}")
            
        except subprocess.CalledProcessError as e:
            if "nothing to commit" in e.stderr:
                self.log.info("No changes to commit")
            else:
                raise
        except Exception as e:
            self.log.error(f"Failed to commit session changes: {e}")
            raise