import subprocess
import os
import platform

# Path to the custom lynx config file
lynx_config_path = os.path.join(os.path.dirname(__file__), 'lynx.cfg')
if platform.system() == 'Linux':
    lynx_path = '/usr/bin/lynx'
else:
    lynx_path = 'lynx'


def lynx_url(url: str) -> str:
    """Fetch a webpage using Lynx with a custom config and return the text output."""
    try:
        # Run the Lynx command with the custom config file and a 15-second timeout
        result = subprocess.run(
            [lynx_path, url, '-dump', '-cfg=', lynx_config_path, '--display_charset=utf-8', '-accept_all_cookies'],
#            ['lynx',  url, '-dump', '--display_charset=utf-8'],
            capture_output=True,
            text=True,
            check=True,
            timeout=15  # Set timeout to 15 seconds
        )

        return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("The Lynx request timed out after 15 seconds.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to fetch the page with Lynx: {str(e)}")
    except FileNotFoundError as e:
        raise RuntimeError(f"Lynx not found: {str(e)}")