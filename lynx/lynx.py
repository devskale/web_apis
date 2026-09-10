import subprocess
import platform

if platform.system() == 'Linux':
    lynx_path = '/usr/bin/lynx'
else:
    lynx_path = 'lynx'


def lynx_url(url: str) -> str:
    """Fetch a webpage using Lynx and return the text output.

    Uses the system lynx config: passing -cfg would replace it wholesale
    (which breaks HTTPS resolution on this box). Cookie handling is covered
    by the -accept_all_cookies flag and lynx's defaults instead.
    """
    try:
        result = subprocess.run(
            [lynx_path, '-dump', '-display_charset=utf-8',
             '-accept_all_cookies', url],
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
