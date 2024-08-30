# w3m/w3m.py

import subprocess
import os

# Path to the custom w3m config file
w3m_config_path = os.path.join(os.path.dirname(__file__), 'config')

def fetch_with_w3m(url: str) -> str:
    """Fetch a webpage using w3m with a custom config and return the text output."""
    try:
#        print("Executing w3m with the following command:")
#        print(['/usr/bin/w3m', '-config', w3m_config_path, '-dump', url])
#        print("Current PATH:", os.environ["PATH"])

        # Run the w3m command with the custom config file and a 15-second timeout
        result = subprocess.run(
            ['/usr/bin/w3m', '-config', w3m_config_path, '-dump', url],
#            ['w3m', '-config', w3m_config_path, '-dump', url],
#            ['/usr/bin/w3m', '-dump', url],
            capture_output=True,
            text=True,
            check=True,
            timeout=15  # Set timeout to 15 seconds
        )

        return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("The w3m request timed out after 15 seconds.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to fetch the page with w3m: {str(e)}")
    except FileNotFoundError as e:
        raise RuntimeError(f"w3m not found: {str(e)}")