#!/usr/bin/env python3
import json
import sys
import subprocess
from pathlib import Path
import hashlib
from datetime import datetime
import os
import traceback

def get_last_interaction(transcript_path):
    """Extract the last user prompt and LLM's response from the transcript.
    Currently assumes Claude Code transcripts
    """
    print(f"get_last_interaction {transcript_path}")
    try:
        with open(transcript_path, 'r') as f:
            lines = f.readlines()
        print(lines)
        
        # Parse JSONL (one JSON object per line)
        events = [json.loads(line) for line in lines if line.strip()]
        
        print(events)
        for e in events:
            print(json.dumps(e, indent=4))
        # Find the last user message
        user_messages =[] #= [e for e in events if e['message'].get('role') == 'user']
        for i,e in enumerate(events):
            print(i, e)
            try:
                print(e['message'])
                if e['message'].get('role') == 'user':
                    user_messages.append(e)
            except Exception as err:
                print(err)
        print("user_messages", user_messages)
        if not user_messages:
            return None, None
        
        last_user = user_messages[-1]
        last_user_ts = datetime.fromisoformat(last_user.get('timestamp', 0))

        # Find Claude's responses after the last user message
        assistant_messages =[] #= [e for e in events if e['message'].get('role') == 'user']
        for i,e in enumerate(events):
            print(i, e)
            try:
                print(e['message'])
                e_ts = datetime.fromisoformat(e.get('timestamp',0))
                if e['message'].get('role') == 'assistant' and e_ts>last_user_ts:
                    assistant_messages.append(e)
            except Exception as err:
                print(err)
        print("assistant_messages", assistant_messages)
        
        # Extract text content
        prompt = last_user['message']['content']#""
#        if last_user.get('content'):
#            for content in last_user['content']:
#                if content.get('type') == 'text':
#                    prompt = content.get('text', '')
#                    break
        
        response = ""
        if assistant_messages:
            first_assistant = assistant_messages[0]['message']
            if first_assistant.get('content'):
                for content in first_assistant['content']:
                    if content.get('type') == 'text':
                        response = content.get('text', '')
                        break
        
        return prompt, response
    
    except Exception as e:
        print(f"Error reading transcript: {e}", file=sys.stderr)
        return None, None
    
def calculate_sha256(filepath):
    """Calculate SHA-256 hash of a file."""
    # note that this can be replaced with hashlib.file_digest().hexdigest() from python >=3.11

    sha256_hash = hashlib.sha256()
    BUF_SIZE = 65536  #  read stuff in 64kb chunks
    try:
        with open(filepath, "rb") as f:
            # Read in chunks to handle large files efficiently
            for byte_block in iter(lambda: f.read(BUF_SIZE), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"Error: {str(e)}"


def create_commit(prompt, response):
    """Create a git commit with the prompt and response."""
    try:

        # Get Git Repo Path
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        repo_path = Path(result.stdout.strip())   

        # Stage all changes
        subprocess.run(['git', 'add', '-A'], check=True)
        
        # Check if there are changes to commit
        result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            capture_output=True
        )
        
        if result.returncode == 0:
            print("No changes to commit")
            return
        
        # Truncate prompt and response for commit message
        prompt_preview = prompt[:500] if prompt else "(no prompt)"
        response_preview = response[:500] if response else "(no response)"
        
        commit_msg = f"""LLM Code Interaction

Prompt: {prompt_preview}

Response: {response_preview}"""
        
        # Skip large files, but record the skips
        # Size threshold in bytes (e.g., 10MB)
        MAX_FILE_SIZE = 10 * 1024 * 1024
        # Get staged files
        result = subprocess.run(
            ["git", "diff", "--staged", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
            #cwd=project_dir
        )
        staged_files = result.stdout.strip().split('\n')

        large_files = []
        for filepath in staged_files:
            if not filepath:
                continue
            
            full_path = repo_path / filepath
            if not full_path.exists():
                continue
            
            file_size = full_path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                sha_hash = calculate_sha256(filepath)
                large_files.append((filepath, file_size, sha_hash))
        
        if large_files:
            # Unstage large files
            for filepath, size, sha_hash in large_files:
                subprocess.run(["git", "reset", "HEAD", filepath], cwd=repo_path)
            
            commit_msg += f"""\nPrevented commit of {len(large_files)} large file(s) (>{MAX_FILE_SIZE/(1024*1024):.0f}MB):\n"""            
            for filepath, size, sha_hash in large_files:
                size_mb = size / (1024 * 1024)
                commit_msg += f"  - {filepath} ({size_mb:.2f} MB) SHA256: {sha_hash}\n"

        # Create the commit
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True)
        print("✓ Created commit for this interaction")
        
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error creating commit: {e}", file=sys.stderr)

def write_to_conversation_file(prompt, response, filename):
    # Get project directory
    #project_dir = Path(input_data.get("cwd", "."))
    #conversation_file = project_dir / "claude-conversations.md"
    conversation_file = Path(filename)

    # Format the entry
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"""---

## {timestamp}

**User:**
{prompt}

**LLM:**
{response}

"""

    # Append to the file
    with open(conversation_file, 'a') as f:
        if conversation_file.stat().st_size == 0:
            f.write("# LLM Conversations\n")
        f.write(entry)

    print(f"Saved conversation to {conversation_file}")

def main():
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)
        
        transcript_path = input_data.get('transcript_path')
        if not transcript_path:
            print("Error: No transcript path provided", file=sys.stderr)
            sys.exit(1)

        # Get current branch
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )

        # Get session information (using git-branch as session)        
        branch = result.stdout.strip()
        if not branch:
            branch = "detached-HEAD"
        branch.replace('/', '-').replace(' ', '_') # remove problematic characters        

        session_dir = Path(f"llm-sessions/{branch}/")
        session_dir.mkdir(parents=True, exist_ok=True)


        # copy transcript to llm-sessions/<session> dir
        import shutil
        transcript_path = Path(transcript_path)
        destination = session_dir / "claude_transcript" / transcript_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(transcript_path, destination)

        try:
            # Get the last interaction
            prompt, response = get_last_interaction(transcript_path)
            
            if prompt is None:
                print("Error: Could not extract interaction from transcript", file=sys.stderr)

            # write prompt to to file
            write_to_conversation_file(prompt, response, filename= session_dir / f"conversation-{branch}.md")
        finally:
            # Create the commit, if in session
            if branch.startswith("session-"):
                create_commit(prompt, response)
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e} \n {traceback.print_exc()}")
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()