#!/usr/bin/env python3
"""
checkopenhabfiles.py - Validates openHAB items, rules and sitemap files.

Usage:
  python checkopenhabfiles.py /etc/openhab
  python checkopenhabfiles.py "\\\\myopenhabip\\openHAB-conf"
"""

import sys
import os
import re
import glob


# ---------------------------------------------------------------------------
# Strip // line comments and /* */ block comments from a list of lines.
# Returns a new list of cleaned lines (empty string for fully commented lines).
# ---------------------------------------------------------------------------
def strip_comments(lines):
    result = []
    in_block = False
    for line in lines:
        cleaned = []
        j = 0
        while j < len(line):
            if in_block:
                if line[j:j+2] == '*/':
                    in_block = False
                    j += 2
                else:
                    j += 1
            else:
                if line[j:j+2] == '/*':
                    in_block = True
                    j += 2
                elif line[j:j+2] == '//':
                    break  # rest of line is a comment
                else:
                    cleaned.append(line[j])
                    j += 1
        result.append(''.join(cleaned))
    return result


def make_slash(path):
    """Ensure path ends with the OS path separator."""
    return path if path.endswith(os.sep) else path + os.sep


def read_lines(filepath):
    with open(filepath, encoding='utf-8') as f:
        return f.read().splitlines()


def get_files(folder, extension):
    pattern = os.path.join(folder, f'*{extension}')
    return glob.glob(pattern)


# ---------------------------------------------------------------------------
# Extract Thing UIDs from .things files.
# Handles:
#   - Top-level:  Thing binding:type:id "..."
#                 Bridge binding:type:id "..." { ... }
#                 binding:type:id [...]          (no keyword)
#                 binding:type:id:subid [...]    (4-segment)
#   - Nested inside Bridge { }: Thing type id "..."
# ---------------------------------------------------------------------------
def extract_thing_names(folder):
    things = set()

    TOP_LEVEL_PATTERN = re.compile(
        r'^\s*(?:(?:Bridge|Thing)\s+)?'
        r'([a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+(?::[a-zA-Z0-9_-]+)?)',
        re.IGNORECASE
    )
    INNER_BRIDGE_PATTERN = re.compile(
        r'^\s*Bridge\s+([a-zA-Z0-9_-]+)\s+([a-zA-Z0-9_-]+)',
        re.IGNORECASE
    )
    NESTED_THING_PATTERN = re.compile(
        r'^\s*Thing\s+([a-zA-Z0-9_-]+)\s+([a-zA-Z0-9_-]+)',
        re.IGNORECASE
    )
    BRIDGE_PATTERN = re.compile(r'^\s*Bridge\b', re.IGNORECASE)

    for filepath in get_files(folder, '.things'):
        raw_lines = read_lines(filepath)
        clean_lines = strip_comments(raw_lines)

        current_bridge_uid = ''
        current_inner_bridge_id = ''
        brace_depth = 0
        bridge_entry_depth = 0
        inner_bridge_entry_depth = 0

        for line in clean_lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            for c in trimmed:
                if c == '{':
                    brace_depth += 1
                elif c == '}':
                    brace_depth -= 1

            if current_bridge_uid:
                # Prüfen, ob eine innere Bridge startet (z. B. Bridge poller Temperatures)
                m_inner = INNER_BRIDGE_PATTERN.match(line)
                if m_inner:
                    current_inner_bridge_id = m_inner.group(2).strip()
                    inner_bridge_entry_depth = brace_depth - trimmed.count('{')

                # Verschachteltes Thing auslesen
                m = NESTED_THING_PATTERN.match(line)
                if m:
                    parts = current_bridge_uid.split(':')
                    if len(parts) == 3:
                        # Wenn wir uns innerhalb einer Poller-Bridge befinden
                        if current_inner_bridge_id and brace_depth > inner_bridge_entry_depth:
                            # 5-teilige UID (Modbus-Style: binding:data:bridgeId:pollerId:thingId)
                            full_uid = f'{parts[0]}:{m.group(1)}:{parts[2]}:{current_inner_bridge_id}:{m.group(2)}'
                        else:
                            # 4-teilige UID (Standard-Style)
                            full_uid = f'{parts[0]}:{m.group(1)}:{parts[2]}:{m.group(2)}'
                        things.add(full_uid)

                # Innere Bridge verlassen
                if current_inner_bridge_id and brace_depth <= inner_bridge_entry_depth:
                    current_inner_bridge_id = ''

                # Haupt-Bridge verlassen
                if brace_depth <= bridge_entry_depth:
                    current_bridge_uid = ''
                    current_inner_bridge_id = ''
            else:
                m = TOP_LEVEL_PATTERN.match(line)
                if m:
                    things.add(m.group(1).strip())

                    if BRIDGE_PATTERN.match(line):
                        current_bridge_uid = m.group(1).strip()
                        bridge_entry_depth = brace_depth - trimmed.count('{')

    return things

# ---------------------------------------------------------------------------
# Extract Item names from .items files.
# ---------------------------------------------------------------------------
def extract_item_names(folder):
    items = set()
    ITEM_PATTERN = re.compile(
        r'^\s*(?:Group|Switch|Rollershutter|String|Number|Dimmer|Contact|'
        r'DateTime|Color|Player|Location|Image)(?::[a-zA-Z0-9_]+)?\s+([a-zA-Z0-9_]+)',
        re.IGNORECASE
    )
    for filepath in get_files(folder, '.items'):
        raw_lines = read_lines(filepath)
        clean_lines = strip_comments(raw_lines)
        for line in clean_lines:
            m = ITEM_PATTERN.match(line)
            if m:
                items.add(m.group(1))
    return items


# ---------------------------------------------------------------------------
# Validate item→thing channel links in .items files.
# ---------------------------------------------------------------------------
def validate_item_thing_links(folder, valid_things, errors):
    ITEM_NAME_PATTERN = re.compile(
        r'^\s*(?:Group|Switch|Rollershutter|String|Number|Dimmer|Contact|'
        r'DateTime|Color|Player|Location|Image)(?::[a-zA-Z0-9_]+)?\s+([a-zA-Z0-9_]+)',
        re.IGNORECASE
    )
    CHANNEL_PATTERN = re.compile(
        r'channel\s*=\s*["\']([^"\']+)["\']',
        re.IGNORECASE
    )
    for filepath in get_files(folder, '.items'):
        filename = os.path.basename(filepath)
        raw_lines = read_lines(filepath)
        clean_lines = strip_comments(raw_lines)
        for line in clean_lines:
            m_item = ITEM_NAME_PATTERN.match(line)
            if not m_item:
                continue
            item_name = m_item.group(1)
            m_chan = CHANNEL_PATTERN.search(line)
            if not m_chan:
                continue
            full_channel = m_chan.group(1)
            last_colon = full_channel.rfind(':')
            second_last = full_channel.rfind(':', 0, last_colon)
            if second_last > 0:
                thing_uid = full_channel[:second_last]

# ---------------------------------------------------------------------------
# Validate item/thing references in .rules files.
# ---------------------------------------------------------------------------
def validate_rule_item_links(folder, valid_things, valid_items, errors):
    IMPLICIT_VARS = {'triggeringItem', 'newState', 'previousState', 'receivedCommand', 'receivedEvent'}
    METHOD_PATTERN  = re.compile(r'\b([a-zA-Z0-9_]+)\.(?:state|sendCommand|postUpdate)\b')
    ACTION_PATTERN  = re.compile(r'(?<!\.)(?:sendCommand|postUpdate)\s*\(\s*["\']([a-zA-Z0-9_]+)["\']')
    THING_PATTERN   = re.compile(r'\bgetThingStatusInfo\s*\(\s*["\']([a-zA-Z0-9_]+)["\']')

    for filepath in get_files(folder, '.rules'):
        filename = os.path.basename(filepath)
        raw_lines = read_lines(filepath)
        clean_lines = strip_comments(raw_lines)
        for line_num, line in enumerate(clean_lines, start=1):
            if not line.strip():
                continue

            for m in METHOD_PATTERN.finditer(line):
                ref = m.group(1)
                if ref in IMPLICIT_VARS:
                    continue
                if ref not in valid_items:
                    errors.append(
                        f'[{filename}: Line {line_num}] Invalid Item Method: "{ref}"'
                    )

            for m in ACTION_PATTERN.finditer(line):
                ref = m.group(1)
                if ref not in valid_items:
                    errors.append(
                        f'[{filename}: Line {line_num}] Invalid Item Action Target: "{ref}"'
                    )

            for m in THING_PATTERN.finditer(line):
                ref = m.group(1)
                if ref not in valid_things:
                    errors.append(
                        f'[{filename}: Line {line_num}] Invalid Thing Reference: "{ref}"'
                    )


# ---------------------------------------------------------------------------
# Validate item references in .sitemap files.
# ---------------------------------------------------------------------------
def validate_sitemap_item_links(folder, valid_items, errors):
    ITEM_PATTERN           = re.compile(r'\bitem\s*=\s*([a-zA-Z0-9_]+)', re.IGNORECASE)
    CONDITION_BLOCK_PATTERN = re.compile(
        r'\b(?:visibility|valuecolor|labelcolor|iconcolor)\s*=\s*\[([^\]]+)\]',
        re.IGNORECASE
    )
    ITEM_IN_CONDITION_PATTERN = re.compile(
        r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:==|!=|>=|<=|>|<)'
    )

    for filepath in get_files(folder, '.sitemap'):
        filename = os.path.basename(filepath)
        raw_lines = read_lines(filepath)
        clean_lines = strip_comments(raw_lines)
        for line_num, line in enumerate(clean_lines, start=1):
            if not line.strip():
                continue

            # 1. Widget item bindings
            for m in ITEM_PATTERN.finditer(line):
                ref = m.group(1)
                if ref not in valid_items:
                    errors.append(
                        f'[{filename}: Line {line_num}] '
                        f'Invalid Sitemap Item Widget Binding: "{ref}"'
                    )

            # 2. Conditional blocks (visibility, valuecolor, etc.)
            for m in CONDITION_BLOCK_PATTERN.finditer(line):
                block_content = m.group(1)
                for sm in ITEM_IN_CONDITION_PATTERN.finditer(block_content):
                    ref = sm.group(1)
                    if ref not in valid_items:
                        errors.append(
                            f'[{filename}: Line {line_num}] '
                            f'Invalid Conditional Rule Item Reference: "{ref}"'
                        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def check_oh(oh_folder):
    errors = []
    folder = make_slash(oh_folder)

    things_dir  = os.path.join(folder, 'things')
    items_dir   = os.path.join(folder, 'items')
    rules_dir   = os.path.join(folder, 'rules')
    sitemaps_dir = os.path.join(folder, 'sitemaps')

    # openHAB folder names are case-insensitive on Windows but case-sensitive on Linux.
    # Try to find the actual capitalisation if the lower-case variant doesn't exist.
    def resolve_dir(base, name):
        lower = os.path.join(base, name.lower())
        if os.path.isdir(lower):
            return lower
        title = os.path.join(base, name.title())
        if os.path.isdir(title):
            return title
        return lower  # fall back; error will be reported naturally

    things_dir   = resolve_dir(folder, 'things')
    items_dir    = resolve_dir(folder, 'items')
    rules_dir    = resolve_dir(folder, 'rules')
    sitemaps_dir = resolve_dir(folder, 'sitemaps')

    if not os.path.isdir(things_dir):
        print(f'Folder does not exist: {things_dir}')
        return -1

    things = extract_thing_names(things_dir)
    items  = extract_item_names(items_dir)

    validate_item_thing_links(items_dir,   things, errors)
    validate_sitemap_item_links(sitemaps_dir, items,  errors)
    validate_rule_item_links(rules_dir,    things, items, errors)

    return errors


def main():
    if len(sys.argv) < 2:
        print(f'Usage: python {sys.argv[0]} <openhab-conf-folder>')
        sys.exit(1)

    oh_folder = sys.argv[1]
    errors = check_oh(oh_folder)

    if errors == -1:
        sys.exit(1)

    for e in errors:
        print(e)

    if errors:
        print(f'{len(errors)} errors found')
        sys.exit(1)
    else:
        print('No errors found in items, rules and sitemap files')
        sys.exit(0)


if __name__ == '__main__':
    main()
