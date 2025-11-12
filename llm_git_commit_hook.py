#!/usr/bin/env python3
import json
import sys
import subprocess
from pathlib import Path
import hashlib
from datetime import datetime
import os
import traceback
import shutil
import re
from  . import convert_chat_logs


# Setup logging to file
LOG_FILE = Path.home() / "claude_hook_debug.log"

def setup_logging():
    """Redirect all output to a log file."""
    global original_stderr
    original_stderr = sys.stderr
    sys.stderr = open(LOG_FILE, 'a', encoding='utf-8')
    print(f"\n\n{'='*80}", file=sys.stderr)
    print(f"HOOK RUN AT {datetime.now()}", file=sys.stderr)
    print(f"{'='*80}\n", file=sys.stderr)
    sys.stderr.flush()

setup_logging()

def debug_log(msg):
    """Log debug messages."""
    print(f"[DEBUG] {msg}", file=sys.stderr)
    with open(LOG_FILE, 'a') as f:
        f.write("[DEBUG] {msg}\n")
    sys.stderr.flush()

def clean_ansi_codes(text):
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def extract_text_content(message):
    """Extract text content from message object (handles both string and list formats)."""
    if not message:
        debug_log("extract_text_content: message is None or empty")
        return ""
    
    content = message.get('content')
    debug_log(f"extract_text_content: content type = {type(content)}")
    
    # Handle string content
    if isinstance(content, str):
        debug_log(f"extract_text_content: string content, length = {len(content)}")
        return clean_ansi_codes(content)
    
    # Handle list of content blocks
    if isinstance(content, list):
        debug_log(f"extract_text_content: list content, {len(content)} blocks")
        texts = []
        for i, block in enumerate(content):
            block_type = block.get('type') if isinstance(block, dict) else 'not-dict'
            debug_log(f"  Block {i}: type={block_type}")
            if isinstance(block, dict) and block.get('type') == 'text':
                text = block.get('text', '')
                debug_log(f"  Block {i}: extracted {len(text)} chars")
                texts.append(clean_ansi_codes(text))
        result = '\n'.join(texts)
        debug_log(f"extract_text_content: combined text length = {len(result)}")
        return result
    
    debug_log("extract_text_content: unknown content format")
    return ""

def get_last_interaction(transcript_path):
    """Extract the last user prompt and LLM's response from the transcript."""
    debug_log(f"get_last_interaction: Reading transcript: {transcript_path}")
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        debug_log(f"get_last_interaction: Read {len(lines)} lines")
        
        # Parse JSONL (one JSON object per line)
        events = []
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                debug_log(f"get_last_interaction: Could not parse line {line_num}: {e}")
                continue
        
        debug_log(f"get_last_interaction: Parsed {len(events)} events")
        
        if not events:
            debug_log("get_last_interaction: No events found")
            return None, None
        
        # Find all user and assistant messages
        user_messages = []
        assistant_messages = []
        
        for i, entry in enumerate(events):
            try:
                # Skip if no message field
                if 'message' not in entry:
                    continue
                
                message = entry['message']
                role = message.get('role')
                
                if role == 'user':
                    user_messages.append(entry)
                elif role == 'assistant':
                    assistant_messages.append(entry)
                    
            except Exception as err:
                debug_log(f"  Event {i}: error processing - {err}")
                continue
        
        debug_log(f"get_last_interaction: Found {len(user_messages)} user, {len(assistant_messages)} assistant messages")
        
        if not user_messages:
            debug_log("get_last_interaction: No user messages found")
            return None, None
        
        # Find the last user message with actual text content (not just tool results)
        last_user = None
        for user_msg in reversed(user_messages):
            prompt = extract_text_content(user_msg['message'])
            if prompt and prompt.strip():
                last_user = user_msg
                debug_log(f"get_last_interaction: Found user message with text content")
                break
        
        if not last_user:
            debug_log("get_last_interaction: No user messages with text content found")
            return None, None
        
        prompt = extract_text_content(last_user['message'])
        debug_log(f"get_last_interaction: Prompt length = {len(prompt)}")
        
        # Find assistant responses after the last user message with text
        last_user_ts = None
        try:
            if 'timestamp' in last_user:
                last_user_ts = datetime.fromisoformat(last_user['timestamp'])
                debug_log(f"get_last_interaction: Last user timestamp = {last_user_ts}")
        except Exception as e:
            debug_log(f"get_last_interaction: Could not parse user timestamp: {e}")
        
        # Get responses after the last user message
        relevant_assistant = []
        for entry in assistant_messages:
            if last_user_ts:
                try:
                    entry_ts = datetime.fromisoformat(entry.get('timestamp', ''))
                    if entry_ts > last_user_ts:
                        relevant_assistant.append(entry)
                except:
                    relevant_assistant.append(entry)
            else:
                relevant_assistant.append(entry)
        
        debug_log(f"get_last_interaction: Found {len(relevant_assistant)} relevant assistant messages")
        
        # Extract response - look for the first assistant message with text content
        response = ""
        for asst_msg in relevant_assistant:
            response = extract_text_content(asst_msg['message'])
            if response and response.strip():
                debug_log(f"get_last_interaction: Found assistant response with text")
                break
        
        if not response and assistant_messages:
            # Fallback: try to find any assistant message with text
            debug_log("get_last_interaction: Fallback - searching all assistant messages")
            for asst_msg in reversed(assistant_messages):
                response = extract_text_content(asst_msg['message'])
                if response and response.strip():
                    debug_log(f"get_last_interaction: Found assistant response in fallback")
                    break
        
        debug_log(f"get_last_interaction: Response length = {len(response) if response else 0}")
        
        if not response or not response.strip():
            debug_log("get_last_interaction: Could not extract response text")
            return prompt, None
        
        debug_log(f"get_last_interaction: SUCCESS - prompt={len(prompt)} chars, response={len(response)} chars")
        return prompt, response
    
    except Exception as e:
        debug_log(f"get_last_interaction: Exception - {e}")
        traceback.print_exc(file=sys.stderr)
        return None, None
    
def get_new_prompt_and_response(transcript_path, t_start):
    """get the first user prompt and assistant final response
        for new conversation since last git commit on datetime timestamp t_start
        """
    entries = []
    with open(transcript_path, 'rb') as f:
        for line in f:
            j = json.loads(line)
            timestamp_str = j.get('timestamp')
            if timestamp_str:
                t= datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                t = None

            if t and t > t_start:
                entries.append(j)

    for entry in entries:
        if convert_chat_logs.is_noise_message(entry):
            continue

        # first one we find is the "prompt"
        message = entry.get('message', {})
        # Extract content
        content = convert_chat_logs.extract_message_content(message)
        content = convert_chat_logs.clean_ansi_codes(content)

        # Skip empty messages
        if not content or content.strip() == '':
            continue

        prompt = content
        break

    for entry in entries[::-1]:
        if convert_chat_logs.is_noise_message(entry):
            continue

        # last one we find is the "response" (note the [::-1] above)
        message = entry.get('message', {})
        # Extract content
        content = convert_chat_logs.extract_message_content(message)
        content = convert_chat_logs.clean_ansi_codes(content)

        # Skip empty messages
        if not content or content.strip() == '':
            continue

        response = content
        break

    debug_log(f"get_new_prompt_and_response: SUCCESS - prompt={len(prompt)} chars, response={len(response)} chars")
    return prompt, response


def calculate_sha256(filepath):
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    BUF_SIZE = 65536
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(BUF_SIZE), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"Error: {str(e)}"

def push_to_remote(branch_name):
    """Push the current branch to remote."""
    try:
        debug_log(f"push_to_remote: Checking upstream for branch {branch_name}")
        
        # Check if branch has an upstream
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', f'{branch_name}@{{upstream}}'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            # Upstream exists, just push
            debug_log("push_to_remote: Upstream exists, pushing...")
            result = subprocess.run(['git', 'push'], check=True, capture_output=True, text=True)
            debug_log(f"push_to_remote: Push stdout: {result.stdout}")
            debug_log(f"push_to_remote: Push stderr: {result.stderr}")
            print("✓ Pushed to remote", file=sys.stderr)
        else:
            # No upstream, set it and push
            debug_log(f"push_to_remote: No upstream, setting and pushing to origin/{branch_name}")
            result = subprocess.run(
                ['git', 'push', '--set-upstream', 'origin', branch_name],
                check=True,
                capture_output=True,
                text=True
            )
            debug_log(f"push_to_remote: Push stdout: {result.stdout}")
            debug_log(f"push_to_remote: Push stderr: {result.stderr}")
            print("✓ Pushed to remote (upstream set)", file=sys.stderr)
            
    except subprocess.CalledProcessError as e:
        debug_log(f"push_to_remote: CalledProcessError - returncode={e.returncode}")
        debug_log(f"push_to_remote: stdout={e.stdout}")
        debug_log(f"push_to_remote: stderr={e.stderr}")
        print(f"Warning: Failed to push to remote: {e.stderr if e.stderr else str(e)}", file=sys.stderr)
        print("Commit was created locally but not pushed", file=sys.stderr)
    except Exception as e:
        debug_log(f"push_to_remote: Exception - {e}")
        traceback.print_exc(file=sys.stderr)
        print(f"Warning: Failed to push to remote: {e}", file=sys.stderr)

def create_commit(prompt, response, branch_name):
    """Create a git commit with the prompt and response, then push."""
    try:
        debug_log("create_commit: Starting commit process")
        
        # Get Git Repo Path
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        repo_path = Path(result.stdout.strip())
        debug_log(f"create_commit: Repo path = {repo_path}")

        # Stage all changes
        debug_log("create_commit: Staging all changes (git add -A)")
        subprocess.run(['git', 'add', '-A'], check=True)
        
        # Check if there are changes to commit
        debug_log("create_commit: Checking for staged changes")
        result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            capture_output=True
        )
        
        if result.returncode == 0:
            debug_log("create_commit: No changes to commit")
            print("No changes to commit", file=sys.stderr)
            return
        
        debug_log("create_commit: Changes detected, creating commit message")
        
        # Truncate prompt and response for commit message
        prompt_preview = prompt[:500] if prompt else "(no prompt)"
        response_preview = response[:500] if response else "(no response)"
        
        commit_msg = f"""LLM: {prompt_preview[:70]}

Prompt: {prompt_preview}

Response: {response_preview}"""
        
        # Skip large files, but record the skips
        MAX_FILE_SIZE = 10 * 1024 * 1024
        debug_log("create_commit: Checking for large files")
        result = subprocess.run(
            ["git", "diff", "--staged", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        staged_files = result.stdout.strip().split('\n')
        debug_log(f"create_commit: {len(staged_files)} staged files")

        large_files = []
        for filepath in staged_files:
            if not filepath:
                continue
            
            full_path = repo_path / filepath
            if not full_path.exists():
                continue
            
            file_size = full_path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                sha_hash = calculate_sha256(full_path)
                large_files.append((filepath, file_size, sha_hash))
        
        if large_files:
            debug_log(f"create_commit: Found {len(large_files)} large files, unstaging")
            for filepath, size, sha_hash in large_files:
                subprocess.run(["git", "reset", "HEAD", filepath], cwd=repo_path)
            
            commit_msg += f"""\n\nPrevented commit of {len(large_files)} large file(s) (>{MAX_FILE_SIZE/(1024*1024):.0f}MB):\n"""            
            for filepath, size, sha_hash in large_files:
                size_mb = size / (1024 * 1024)
                commit_msg += f"  - {filepath} ({size_mb:.2f} MB) SHA256: {sha_hash}\n"

        # Create the commit
        debug_log("create_commit: Creating commit")
        debug_log(f"create_commit: Commit message preview: {commit_msg[:200]}...")
        result = subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True, text=True)
        debug_log(f"create_commit: Commit stdout: {result.stdout}")
        debug_log(f"create_commit: Commit stderr: {result.stderr}")
        print("✓ Created commit for this interaction", file=sys.stderr)
        
        # Push to remote
        # debug_log("create_commit: Calling push_to_remote")
        # push_to_remote(branch_name)
        debug_log("create_commit: Completed")
        
    except subprocess.CalledProcessError as e:
        debug_log(f"create_commit: CalledProcessError - returncode={e.returncode}")
        debug_log(f"create_commit: stdout={e.stdout}")
        debug_log(f"create_commit: stderr={e.stderr}")
        print(f"Git error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    except Exception as e:
        debug_log(f"create_commit: Exception - {e}")
        traceback.print_exc(file=sys.stderr)
        print(f"Error creating commit: {e}", file=sys.stderr)

def write_to_conversation_file(prompt, response, filename):
    """Append interaction to conversation markdown file."""
    debug_log(f"write_to_conversation_file: Writing to {filename}")
    conversation_file = Path(filename)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"""---

## {timestamp}

**User:**
{prompt}

**LLM:**
{response}

"""

    try:
        with open(conversation_file, 'a', encoding='utf-8') as f:
            if conversation_file.exists() and conversation_file.stat().st_size == 0:
                f.write("# LLM Conversations\n\n")
            f.write(entry)
        
        debug_log(f"write_to_conversation_file: Saved {len(entry)} bytes")
        print(f"Saved conversation to {conversation_file}", file=sys.stderr)
    except Exception as e:
        debug_log(f"write_to_conversation_file: Exception - {e}")
        traceback.print_exc(file=sys.stderr)
        print(f"Error writing conversation file: {e}", file=sys.stderr)

def main():
    debug_log("=== HOOK STARTED ===")
    try:
        # Read hook input from stdin
        debug_log("main: Reading input from stdin")
        input_data = json.load(sys.stdin)
        debug_log(f"main: Input data keys: {list(input_data.keys())}")
        
        transcript_path = input_data.get('transcript_path')
        debug_log(f"main: transcript_path = {transcript_path}")

        claude_session_id = input_data.get('session_id')
        
        if not transcript_path:
            debug_log("main: ERROR - No transcript path provided")
            print("Error: No transcript path provided", file=sys.stderr)
            sys.exit(1)

        # Get current branch
        debug_log("main: Getting current branch")
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )

        branch = result.stdout.strip()
        debug_log(f"main: Current branch = {branch}")

        if not branch:
            branch = "detached-HEAD"
        branch_clean = branch.replace('/', '-').replace(' ', '_')
        debug_log(f"main: Cleaned branch name = {branch_clean}")

        session_dir = Path(f"llm-sessions/{branch_clean}/")
        debug_log(f"main: Session dir = {session_dir}")
        session_dir.mkdir(parents=True, exist_ok=True)

        # Git timestamp of previous commit
        try:
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%ci'],
                capture_output=True,
                text=True
            )
            t_git = datetime.fromisoformat(result.stdout.strip())
        except Exception as err:
            debug_log(f"main: failed to get git timestamp {err}")
            t_git = None



        # Copy transcript
        debug_log("main: Copying transcript")
        transcript_path = Path(transcript_path)
        destination = session_dir / "claude_transcript" / transcript_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(transcript_path, destination)
        debug_log(f"main: Transcript copied to {destination}")

        # Get the last interaction
        debug_log("main: Calling get_last_interaction")
        #prompt, response = get_last_interaction(transcript_path)
        if not t_git:
            t_git = datetime.fromtimestamp(0)
        prompt, response = get_new_prompt_and_response(transcript_path, t_git)

        debug_log(f"main: get_last_interaction returned prompt={prompt is not None}, response={response is not None}")
        
        # If no valid interaction, exit gracefully
        if prompt is None or response is None:
            debug_log("main: No valid LLM interaction found, exiting")
            print("No valid LLM interaction found in transcript. Skipping LLM commit.", file=sys.stderr)
            sys.exit(0)


        # Write to conversation file (new version)
        from convert_chat_logs import convert_jsonl_to_markdown
        convert_jsonl_to_markdown(transcript_path,session_dir / f"conversation-{branch_clean}-{claude_session_id}.md" )

        # # Write to conversation file
        # debug_log("main: Writing to conversation file")
        # write_to_conversation_file(
        #     prompt, 
        #     response, 
        #     filename=session_dir / f"conversation-{branch_clean}.md"
        # )
        
        # Create commit and push
        if branch.startswith("session-"):
            debug_log(f"main: On session branch, creating commit")
            create_commit(prompt, response, branch)
        else:
            debug_log(f"main: Not on session branch ({branch}), skipping commit")
            print(f"Not on a session branch ({branch}), skipping commit", file=sys.stderr)
        
        debug_log("=== HOOK COMPLETED SUCCESSFULLY ===")
        
    except json.JSONDecodeError as e:
        debug_log(f"main: JSONDecodeError - {e}")
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        debug_log(f"main: Unexpected exception - {e}")
        print(f"Unexpected error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        sys.stderr.flush()
        sys.stderr.close()

if __name__ == "__main__":
    main()