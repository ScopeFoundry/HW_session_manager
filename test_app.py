#!/usr/bin/env python3

import sys
from pathlib import Path

# Add the main ScopeFoundry path to sys.path to import ScopeFoundry modules
scope_foundry_path = Path(__file__).parent.parent.parent / "ScopeFoundry"
sys.path.insert(0, str(scope_foundry_path))

from ScopeFoundry import BaseMicroscopeApp
from git_session_manager_hw import GitSessionManagerHW


class GitSessionManagerTestApp(BaseMicroscopeApp):
    """Test application for the Git Session Manager hardware component"""
    
    name = "git_session_manager_test_app"
    
    def setup(self):
        """Set up the test application with the git session manager"""
        
        # Add the git session manager hardware
        self.add_hardware(GitSessionManagerHW)
        
        # You can add other hardware or measurements here if needed
        print("Git Session Manager Test App initialized")
        
    def setup_ui(self):
        """Set up the user interface"""
        # Call the parent setup_ui to create the default interface
        BaseMicroscopeApp.setup_ui(self)
        
        # Add custom UI elements if needed
        self.ui.statusbar.showMessage("Git Session Manager Test App Ready")


if __name__ == "__main__":
    import sys
    
    app = GitSessionManagerTestApp(sys.argv)
    app.exec_()