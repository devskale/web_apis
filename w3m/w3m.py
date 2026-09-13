# w3m/w3m.py

import subprocess
import os
import platform

# Path to the custom w3m config file
w3m_config_path = os.path.join(os.path.dirname(__file__), 'config')


def fetch_with_w3m(url: str, links=True) -> str:
    """Fetch a webpage using w3m with a custom config and return the text output."""
    # Determine the correct path for w3m based on the OS
    if platform.system() == 'Linux':
        w3m_path = '/usr/bin/w3m'
    else:
        w3m_path = 'w3m'

    try:
        # links=True adds numbered link references to the dump
        display_link_number = 1 if links else 0
        result = subprocess.run(
            [w3m_path, '-config', w3m_config_path, '-o',
             f'display_link_number={display_link_number}', url, '-dump'],
            capture_output=True,
            text=True,
            check=True,
            timeout=15
        )
        return result.stdout

    except subprocess.TimeoutExpired:
        raise RuntimeError("The w3m request timed out after 15 seconds.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to fetch the page with w3m: {str(e)}")
    except FileNotFoundError as e:
        raise RuntimeError(f"w3m not found: {str(e)}")
