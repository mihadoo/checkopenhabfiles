# checkopenhabfiles.py

A command-line tool that validates [openHAB](https://www.openhab.org/) configuration files — things, items, rules, and sitemaps — and reports broken references.

## What it checks

| Check | Description |
|---|---|
| **Item → Thing links** | Every `channel="..."` binding in `.items` files references a Thing that actually exists in `.things` files |
| **Sitemap → Item links** | Every `item=` reference in `.sitemap` files points to a defined item |
| **Sitemap conditions** | Item names used inside `visibility`, `valuecolor`, `labelcolor` and `iconcolor` blocks are valid |
| **Rule → Item references** | Item names used with `.sendCommand()`, `.postUpdate()`, `sendCommand("ItemName", ...)` and `postUpdate("ItemName", ...)` in `.rules` files are valid |
| **Rule → Thing references** | Thing UIDs passed to `getThingStatusInfo("...")` in `.rules` files are valid |

All checks are **case-sensitive**, matching openHAB's own behaviour.

## What it understands

- `//` line comments and `/* */` block comments are ignored in all file types
- Top-level Things and Bridges with 3- or 4-segment UIDs (`binding:type:id` or `binding:type:bridgeid:id`)
- Things defined without a keyword prefix (`ntp:ntp:local [...]`)
- Nested Things inside Bridge blocks, with the full UID reconstructed automatically:
  ```
  Bridge amazonechocontrol:account:myaccount "..." {
      Thing echo   livingroom   "Alexa Living Room"   [serialNumber="..."]
      // → registered as amazonechocontrol:echo:myaccount:livingroom
  }
  ```
- Bridge blocks where `{` appears on the same line as the `Bridge` keyword or on the next line
- UTF-8 encoded files (standard for openHAB)

## Requirements

- Python 3.6 or newer
- No external dependencies — standard library only

## Installation

Just download the single file:

```bash
wget https://raw.githubusercontent.com/mihadoo/checkopenhabfiles/main/checkopenhabfiles.py
```

or clone the repository:

```bash
git clone https://github.com/mihadoo/checkopenhabfiles.git
```

## Usage

```bash
# Linux / macOS
python3 checkopenhabfiles.py /etc/openhab

# Windows (local folder)
python checkopenhabfiles.py "C:\openhab\conf"

# Windows (network share)
python checkopenhabfiles.py "\\192.168.1.10\openHAB-conf"
```

The tool expects the standard openHAB configuration folder structure:

```
<openhab-conf>/
├── things/
├── items/
├── rules/
└── sitemaps/
```

## Output

If errors are found, each is printed on its own line, followed by a summary count. The exit code is `1` when errors are found, `0` when the configuration is clean.

**Example output with errors:**
```
MyItem in lights.items (References missing Thing: "mqtt:topic:mybroker:mydevice")
[automation.rules: Line 42] Invalid Item Method: "NonExistentItem"
[home.sitemap: Line 17] Invalid Sitemap Item Widget Binding: "MissingItem"
3 errors found
```

**Example output when clean:**
```
No errors found in items, rules and sitemap files
```

## Typical workflow

Run the checker before applying configuration changes to your openHAB instance:

```bash
python3 checkopenhabfiles.py /etc/openhab && echo "Safe to reload"
```

Or integrate it into a CI pipeline that watches your openHAB configuration repository.

## Limitations

- Only `.things`, `.items`, `.rules`, and `.sitemap` files are scanned (top-level directory, non-recursive)
- DSL rules (`.rules`) are supported; newer Blockly or JavaScript rule files are not checked
- Thing UIDs inside Bridge blocks are assumed to follow the standard `binding:thingType:bridgeId:thingId` pattern
