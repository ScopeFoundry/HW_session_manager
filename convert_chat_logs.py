import json
from pathlib import Path
from datetime import datetime
import re

def parse_timestamp(ts_str):
    """Parse ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return ts_str

def clean_ansi_codes(text):
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def extract_message_content(message):
    """Extract text content from message object."""
    if isinstance(message, dict):
        if 'content' in message:
            content = message['content']
            if isinstance(content, str):
                return content
            #elif isinstance(content, list):
            else:
                print(f"{type(content)=}")
                # Extract text from content blocks
                texts = []
                for block in content:
                    #print('\t', repr(block))
                    #print(f"{block.keys()=}")
                    if isinstance(block, dict) and block.get('type') == 'text':
                        texts.append(block.get('text', ''))
                    elif isinstance(block, dict) and block.get('type') == 'tool_use':
                        texts.append("```\n" + str(block) + "\n```")
                    elif isinstance(block, dict) and block.get('type') == 'tool_result':
                        texts.append("```\n" + str(block) + "\n```")

                        # if isinstance(block, str):
                        #     texts.append(block)
                        # else:
                        #     for subblock in block.get('content',[]):
                        #         if isinstance(subblock, str):
                        #             texts.append(subblock)
                        #         else:
                        #             #print(subblock)
                        #             x = subblock.get('text','')
                        #             print('tool_result', x)
                        #             texts.append(x)
                    #print(f"{texts=}")
                return '\n'.join(texts)
        elif 'role' in message and 'content' in message:
            return message.get('content', '')
    return str(message)

def is_noise_message(entry):
    """Check if message should be filtered out."""
    msg_type = entry.get('type', '')
    
    # Filter out these types
    if msg_type in ['file-history-snapshot', 'system']:
        return True
    
    # Filter meta messages
    if entry.get('isMeta', False):
        return True
    
    # Filter command outputs (optional - set to False to include them)
    if msg_type == 'user' and 'local-command-stdout' in extract_message_content(entry.get('message', {})):
        return False
    
    return False

def format_message(entry):
    """Format a single message entry as markdown."""
    msg_type = entry.get('type', 'unknown')
    timestamp = parse_timestamp(entry.get('timestamp', ''))
    message = entry.get('message', {})
    uid = entry.get('uuid')
    
    if entry.get('type')=='user' and  isinstance(message.get('content'),str):
        is_actually_user = True
    else:
        is_actually_user = False

    # Extract content
    content = extract_message_content(message)
    content = clean_ansi_codes(content)
    
    # Skip empty messages
    if not content or content.strip() == '':
        return None
    
    # Format based on type
    #if msg_type == 'user':
    #    role = message.get('role', 'user')
    if is_actually_user:
        return f"### 👤 User - {timestamp} [{uid}]\n\n{content}\n"
    elif msg_type == 'user': #not actually user, often tool use
        return f"### 🤖 Tool Use {timestamp} [{uid}]\n\n{content}"
    elif msg_type == 'assistant':
        model = message.get('model', 'unknown')
        usage = message.get('usage', {})
        tokens = usage.get('output_tokens', 'N/A')
        
        header = f"### 🤖 Assistant ({model}) - {timestamp} [{uid}]"
        if tokens != 'N/A':
            header += f" · {tokens} tokens"
        
        return f"{header}\n\n{content}\n"
    else:
        return f"### {timestamp} [{uid}]\n\n{message}"   
        
    return None

def convert_jsonl_to_markdown(jsonl_path, output_path=None, include_metadata=True):
    """Convert JSONL chat log to markdown."""
    jsonl_path = Path(jsonl_path)
    
    if output_path is None:
        output_path = jsonl_path.with_suffix('.md')
    else:
        output_path = Path(output_path)
    
    print(f"Reading {jsonl_path.name}...")
    
    # Read and parse JSON lines
    messages = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                entry = json.loads(line)
                if not is_noise_message(entry):
                    messages.append(entry)
            except json.JSONDecodeError as e:
                print(f"Warning: Could not parse line {line_num}: {e}")
                continue
    
    print(f"Found {len(messages)} messages")
    
    # Sort by timestamp
    messages.sort(key=lambda x: x.get('timestamp', ''))
    
    # Generate markdown
    md_lines = []
    
    # Add header
    md_lines.append(f"# Chat Log: {jsonl_path.stem}\n")
    md_lines.append(f"**Converted**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Extract session metadata if available
    if messages and include_metadata:
        first_msg = messages[0]
        session_id = first_msg.get('sessionId', 'Unknown')
        git_branch = first_msg.get('gitBranch', 'Unknown')
        
        md_lines.append("## Session Information\n")
        md_lines.append(f"- **Session ID**: `{session_id}`")
        md_lines.append(f"- **Git Branch**: `{git_branch}`")
        md_lines.append(f"- **Total Messages**: {len(messages)}\n")
    
    md_lines.append("---\n")
    md_lines.append("## Conversation\n")
    
    # Add messages
    for entry in messages:
        formatted = format_message(entry)
        if formatted:
            md_lines.append(formatted)
            md_lines.append("---\n")
    
    # Write to file
    output_text = '\n'.join(md_lines)
    output_path.write_text(output_text, encoding='utf-8')
    
    print(f"Saved markdown to {output_path}")
    return output_path

def convert_folder(folder_path, output_dir=None):
    """Convert all JSONL files in a folder to markdown."""
    folder_path = Path(folder_path)
    
    jsonl_files = list(folder_path.glob('*.jsonl'))
    if not jsonl_files:
        print(f"No .jsonl files found in {folder_path}")
        return
    
    print(f"Found {len(jsonl_files)} JSONL file(s)\n")
    
    for jsonl_file in jsonl_files:
        print(f"Processing {jsonl_file.name}...")
        
        if output_dir:
            output_path = Path(output_dir) / jsonl_file.with_suffix('.md').name
        else:
            output_path = jsonl_file.with_suffix('.md')
        
        convert_jsonl_to_markdown(jsonl_file, output_path)
        print()

def create_summary(folder_path, output_path=None, output_dir=None):
    """Create a summary of all chat sessions."""
    folder_path = Path(folder_path)
    jsonl_files = list(folder_path.glob('*.jsonl'))
    
    if not jsonl_files:
        print("No JSONL files found")
        return
    
    summary_lines = ["# Chat Sessions Summary\n"]
    summary_lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    summary_lines.append(f"**Total Sessions**: {len(jsonl_files)}\n")
    summary_lines.append("---\n")
    
    for jsonl_file in sorted(jsonl_files):
        # Count messages
        msg_count = 0
        first_timestamp = None
        last_timestamp = None
        git_branch = None
        
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if not is_noise_message(entry):
                        msg_count += 1
                        ts = entry.get('timestamp')
                        if ts:
                            if first_timestamp is None:
                                first_timestamp = ts
                            last_timestamp = ts
                        if git_branch is None:
                            git_branch = entry.get('gitBranch')
                except:
                    continue
        
        summary_lines.append(f"## {jsonl_file.stem}\n")
        summary_lines.append(f"- **File**: `{jsonl_file.name}`")
        summary_lines.append(f"- **Messages**: {msg_count}")
        if git_branch:
            summary_lines.append(f"- **Branch**: `{git_branch}`")
        if first_timestamp:
            summary_lines.append(f"- **Started**: {parse_timestamp(first_timestamp)}")
        if last_timestamp:
            summary_lines.append(f"- **Ended**: {parse_timestamp(last_timestamp)}")
        summary_lines.append("")
    
    # Determine output location
    if output_path is None:
        if output_dir:
            # If output directory specified, put summary there
            output_path = Path(output_dir) / "CHAT_SESSIONS_SUMMARY.md"
        else:
            # Otherwise put in input folder
            output_path = folder_path / "CHAT_SESSIONS_SUMMARY.md"
    else:
        output_path = Path(output_path)
    
    output_path.write_text('\n'.join(summary_lines), encoding='utf-8')
    print(f"Summary saved to {output_path}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python convert_chat_logs.py <file.jsonl>             # Convert single file")
        print("  python convert_chat_logs.py <folder>                 # Convert all .jsonl in folder")
        print("  python convert_chat_logs.py <folder> --summary       # Create summary only")
        print("  python convert_chat_logs.py <path> --output <dir>    # Specify output directory")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    
    create_summary_flag = '--summary' in sys.argv
    
    output_dir = None
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_dir = sys.argv[idx + 1]
    
    if input_path.is_file():
        convert_jsonl_to_markdown(input_path, output_dir)
    elif input_path.is_dir():
        if create_summary_flag:
            create_summary(input_path, output_dir=output_dir)
        else:
            convert_folder(input_path, output_dir)
            create_summary(input_path, output_dir=output_dir)