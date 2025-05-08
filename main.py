import argparse
import subprocess
import schedule
import time
import logging
import os
import hashlib
import yaml
from deepdiff import DeepDiff
import requests
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_argparse():
    """
    Sets up the argument parser for the command-line interface.
    """
    parser = argparse.ArgumentParser(description="A simple scheduler that periodically runs a user-defined command and compares the output to a baseline.")
    parser.add_argument("command", help="The command to execute (e.g., 'cat /etc/config.txt').  Ensure it's safe and doesn't expose sensitive info if it fails.")
    parser.add_argument("baseline", help="Path to the baseline file (YAML or JSON).")
    parser.add_argument("--interval", type=int, default=60, help="Interval in seconds to run the command (default: 60).  Minimum is 10 seconds for resource safety.")
    parser.add_argument("--output", help="Path to output differences to file.")
    parser.add_argument("--format", choices=['yaml', 'json'], default=None, help="Format of the baseline and command output (yaml or json). Autodetect if not specified.  Defaults to YAML if extension is ambiguous.")
    parser.add_argument("--remote", action='store_true', help="Treat the baseline as a URL to fetch the baseline configuration from.")
    
    return parser.parse_args()

def is_valid_interval(interval):
    """
    Validates that the interval is within acceptable bounds to prevent resource exhaustion.
    """
    if interval < 10:
        raise ValueError("Interval must be at least 10 seconds to prevent resource exhaustion.")
    return True

def run_command(command):
    """
    Executes the given command using subprocess and returns the output.

    Args:
        command (str): The command to execute.

    Returns:
        str: The output of the command.  Returns None if the command fails.
    """
    try:
        # Execute the command using subprocess with proper security considerations
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, executable="/bin/bash")  # Explicitly use bash
        output, error = process.communicate()

        if process.returncode != 0:
            logging.error(f"Command execution failed with error: {error.decode()}")
            return None

        return output.decode().strip()

    except subprocess.CalledProcessError as e:
        logging.error(f"Command execution failed: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return None

def load_baseline(baseline_path, format=None, remote=False):
    """
    Loads the baseline configuration from a file or URL.

    Args:
        baseline_path (str): The path to the baseline file or URL.
        format (str, optional): The format of the baseline file (yaml or json). Defaults to None (autodetect).
        remote (bool, optional):  If True, treat the path as a URL.  Defaults to False.

    Returns:
        dict: The baseline configuration as a dictionary.  Returns None if loading fails.
    """

    try:
        if remote:
            response = requests.get(baseline_path)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            content = response.text
        else:
            with open(baseline_path, 'r') as f:
                content = f.read()

        if format is None:
            if baseline_path.lower().endswith('.yaml') or baseline_path.lower().endswith('.yml'):
                format = 'yaml'
            elif baseline_path.lower().endswith('.json'):
                format = 'json'
            else:
                format = 'yaml' # default to yaml if extension is ambiguous.


        if format == 'yaml':
            return yaml.safe_load(content)
        elif format == 'json':
            return json.loads(content)
        else:
            logging.error(f"Unsupported format: {format}")
            return None

    except FileNotFoundError:
        logging.error(f"Baseline file not found: {baseline_path}")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching baseline from URL: {e}")
        return None
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML: {e}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading the baseline: {e}")
        return None

def compare_configurations(baseline, current_config):
    """
    Compares the baseline configuration with the current configuration using DeepDiff.

    Args:
        baseline (dict): The baseline configuration.
        current_config (dict): The current configuration.

    Returns:
        dict: The differences between the configurations as a dictionary.  Returns None if either input is None.
    """
    if baseline is None or current_config is None:
        return None

    try:
        diff = DeepDiff(baseline, current_config, ignore_order=True)
        return diff
    except Exception as e:
        logging.error(f"Error comparing configurations: {e}")
        return None

def save_differences(differences, output_path):
    """
    Saves the detected differences to a file.

    Args:
        differences (dict): The differences between the configurations.
        output_path (str): The path to the output file.
    """
    try:
        with open(output_path, 'w') as f:
            json.dump(differences, f, indent=4)  # Use JSON for easy readability
        logging.info(f"Differences saved to: {output_path}")
    except Exception as e:
        logging.error(f"Error saving differences to file: {e}")

def format_output(config_string, format):
  """
  Formats the string output from a command into a data format.

  Args:
    config_string (str): The configuration as a string.
    format (str, optional): The format to output to (yaml or json).

  Returns:
    dict: The output configuration as a dictionary.
    Returns None if formatting fails.
  """

  try:
    if format == 'yaml':
      return yaml.safe_load(config_string)
    elif format == 'json':
      return json.loads(config_string)
    else:
      # Attempt autodetection
      try:
        return yaml.safe_load(config_string)
      except yaml.YAMLError:
        try:
          return json.loads(config_string)
        except json.JSONDecodeError:
          logging.error("Could not autodetect the configuration format (YAML or JSON), and no format specified.  Returning None.")
          return None

  except yaml.YAMLError as e:
    logging.error(f"Error parsing YAML: {e}")
    return None
  except json.JSONDecodeError as e:
    logging.error(f"Error parsing JSON: {e}")
    return None
  except Exception as e:
    logging.error(f"An unexpected error occurred while loading the baseline: {e}")
    return None

def check_configuration(command, baseline_path, output_path=None, format=None, remote=False):
    """
    Runs the command, loads the baseline, compares the configurations, and saves the differences.

    Args:
        command (str): The command to execute.
        baseline_path (str): The path to the baseline file.
        output_path (str, optional): The path to save the differences to. Defaults to None.
        format (str, optional): The format of the baseline file (yaml or json). Defaults to None.
    """
    logging.info("Running configuration check...")

    # Run the command to get the current configuration
    current_config_string = run_command(command)

    if current_config_string is None:
        logging.error("Failed to retrieve current configuration. Aborting.")
        return

    current_config = None
    if format:
      current_config = format_output(current_config_string, format)
    else:
      current_config = format_output(current_config_string, None)

    if current_config is None:
      logging.error("Failed to parse current configuration. Aborting")
      return

    # Load the baseline configuration
    baseline = load_baseline(baseline_path, format, remote)

    if baseline is None:
        logging.error("Failed to load baseline configuration. Aborting.")
        return

    # Compare the configurations
    differences = compare_configurations(baseline, current_config)

    if differences:
        logging.warning("Configuration drift detected!")
        logging.info(f"Differences: {differences}")

        if output_path:
            save_differences(differences, output_path)
    else:
        logging.info("No configuration drift detected.")

def main():
    """
    Main function to parse arguments, schedule the configuration check, and run the scheduler.
    """
    args = setup_argparse()

    try:
        is_valid_interval(args.interval)
    except ValueError as e:
        logging.error(e)
        return

    # Schedule the configuration check
    schedule.every(args.interval).seconds.do(check_configuration, args.command, args.baseline, args.output, args.format, args.remote)

    logging.info(f"Scheduled configuration check every {args.interval} seconds. Press Ctrl+C to exit.")

    # Run the scheduler
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Exiting...")

if __name__ == "__main__":
    main()

# Usage Examples:
# 1. Check for changes in /etc/config.txt against baseline.yaml every 60 seconds:
#    python main.py "cat /etc/config.txt" baseline.yaml

# 2. Check for changes and save the diffs to output.json:
#    python main.py "cat /etc/config.txt" baseline.yaml --output output.json

# 3. Check using a JSON baseline:
#    python main.py "cat /etc/config.json" baseline.json --format json

# 4. Check for changes in a remote baseline.
#    python main.py "cat /etc/config.txt" https://example.com/baseline.yaml --remote

# Note: Replace placeholder paths with actual file paths for your system. The 'cat' command is just an example and should be replaced with a safer alternative, if possible.