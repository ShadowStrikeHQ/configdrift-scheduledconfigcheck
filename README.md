# configdrift-ScheduledConfigCheck
A simple scheduler that periodically runs a user-defined command (e.g., a configuration extraction script) and compares the output to a baseline. Alerts if differences are found. Uses `schedule` and `subprocess`. - Focused on Detects and reports deviations from baseline configurations across systems or applications. Compares current configurations to a known-good state, highlighting changes that could introduce security vulnerabilities or compliance issues. Supports multiple configuration formats (e.g., YAML, JSON) and remote configuration retrieval.

## Install
`git clone https://github.com/ShadowStrikeHQ/configdrift-scheduledconfigcheck`

## Usage
`./configdrift-scheduledconfigcheck [params]`

## Parameters
- `-h`: Show help message and exit
- `--interval`: No description provided
- `--output`: Path to output differences to file.
- `--format`: No description provided
- `--remote`: Treat the baseline as a URL to fetch the baseline configuration from.

## License
Copyright (c) ShadowStrikeHQ
