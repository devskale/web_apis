# w3m/w3m.py

import subprocess
import os
import re
import urllib.parse
import platform

# Path to the custom w3m config file
w3m_config_path = os.path.join(os.path.dirname(__file__), 'config')

# Determine the correct path for w3m based on the OS
if platform.system() == 'Linux':
    w3m_path = '/usr/bin/w3m'
else:
    w3m_path = 'w3m'


def build_goog_search_url(query: str, num_results: int, domain:str='at') -> str:
    """Construct the Google search URL with the given query and number of results."""
    encoded_query = urllib.parse.quote(query)
    return f"https://www.google.{domain}/search?q={encoded_query}&num={num_results}"


def fetch_with_w3m(url: str) -> str:
    """Fetch a webpage using w3m with a custom config and return the text output."""
    try:
#        print("Executing w3m with the following command:")
#        print(['/usr/bin/w3m', '-config', w3m_config_path, '-dump', url])
#        print("Current PATH:", os.environ["PATH"])
        # on linux w3m is in /usr/bin/w3m
        # on macos w3m is w3m

        # Run the w3m command with the custom config file and a 15-second timeout
        result = subprocess.run(
            [w3m_path, '-config', w3m_config_path, '-dump', url],
#             ['w3m', '-config', w3m_config_path, '-o', 'display_link_number=1', url, '-dump'],
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


def get_numof_qresults(text: str) -> list:
    """Process the text output of a Google search and return the search results."""
    # results is a list of dictionaries containing id, url, and title
    #results = []

    # Initialize max_num to track the highest number in brackets
    max_num = 0

    for line in text.splitlines():
        # Find lines that contain a number in brackets, e.g., [1], [2], etc.
        if "[" in line and "]" in line:
            # Extract the content inside the brackets
            bracket_content = line[line.find("[") + 1 : line.find("]")]
            
            # Check if the content inside the brackets is numeric
            if bracket_content.isdigit():
                num = int(bracket_content)
                # Update max_num if the current number is greater
                if num > max_num:
                    max_num = num
                
            else:
                # Handle non-numeric bracket content as needed
                print(f"Warning: Non-numeric content found in brackets: {num} '{line}'")
                # You could skip this line or handle it differently

    return max_num




def split_result(text: str):
    """Split the text into chunks of '[num] something' until the start of the following [num] or EOF."""
    # Find all occurrences of [num] using a regex pattern
    pattern = re.compile(r'(\[\d+\])')
    matches = pattern.finditer(text)
    
    # Initialize start position
    start_pos = 0
    chunks = []

    # Iterate over the matches
    for match in matches:
        # If this is not the first match, save the previous chunk
        if start_pos != 0:
            chunks.append(text[start_pos:match.start()].strip())
        
        # Update start position to the beginning of the current match
        start_pos = match.start()
    
    # Add the last chunk (from the last match to EOF)
    if start_pos != 0:
        chunks.append(text[start_pos:].strip())

    return chunks


def filtergoo_url(line: str) -> str:
    """Extract the actual target URL from a line of text embedded in a Google redirect URL."""
    # Check if the line contains a Google redirect URL
#    return line
    if '&sa=' in line:
        line = line.split('&sa=')[0]

    google_pattern = re.compile(r'https://[^/]*\.google\.')

    if google_pattern.search(line) and line.count('https://') == 1:
        return 'GGLE'

    google_count = line.lower().count('google')
    https_count = line.lower().count('https')
    if google_count == https_count:
        return 'GGLE'

    # filter out image urls
    if 'https://www.google.' in line and 'imgurl=' in line:
        return 'IMG'
    if 'https://www.google.' in line and 'q=https://www.youtube' in line:
        return 'YOUTUBE'
    if 'https://www.google.' in line and line.count('https://') == 1:
        return 'GGLE'
    if 'https://www.google.' in line and 'https://' in line.split('https://www.google.')[-1]:
        # Split the line by 'https://www.google.' and take the second part
        # Then split again by 'https://' to isolate the actual URL
        url = 'https://' + line.split('https://www.google.')[-1].split('https://', 1)[-1]
        return url
    
    # If no valid structure is found, return the original line or an empty string
    return line




def process_google_search(text: str) -> list:
    """Process the text output of a Google search and return a list of dictionaries indexed by their IDs."""
    # Initialize an empty list that will grow dynamically
    results = []

    # Regex to detect URLs (simple version, might need to be adjusted for specific cases)
    url_pattern = re.compile(r'https?://[^\s]+')

    current_id = None
    current_description = []

    for line in split_result(text):
        # Check for the ID in the line
        if "[" in line and "]" in line:
            # If there is an ongoing description, save it before processing the new ID
            if current_id is not None and current_description:
                while len(results) <= current_id:
                    results.append({"url": None, "description": None})
                # Store the accumulated description
                results[current_id]["description"] = " ".join(current_description).strip()
                current_description = []  # Reset for the next description

            # Extract the content inside the brackets (ID)
            bracket_content = line[line.find("[") + 1 : line.find("]")]
            
            if bracket_content.isdigit():
                current_id = int(bracket_content)

                # Ensure the list is large enough
                while len(results) <= current_id:
                    results.append({"url": None, "description": None})

                # Check if the line contains a URL
                url_match = url_pattern.search(line)
                if url_match:
                    url = url_match.group(0)
#                    results[current_id]["url"] = url
                    results[current_id]["url"] = filtergoo_url(url)
                else:
                    # Otherwise, start accumulating the description
                    description = line[line.find("]") + 1:].strip()
                    if description:
                        current_description.append(description)
            else:
                print(f"Warning: Non-numeric content found in brackets: '{bracket_content}'")

        elif current_id is not None:
            # Continue accumulating lines as part of the description
            current_description.append(line.strip())

    # Handle the last description if it exists
    if current_id is not None and current_description:
        while len(results) <= current_id:
            results.append({"url": None, "description": None})
        results[current_id]["description"] = " ".join(current_description).strip()

    # rerank the results
    # remove all lines with URLs that are not starting with https://
    # start with id=1
    # take description
    reranked_results = []
    idx0 = 1
    for idx, item in enumerate(results):
        if item:
            if item['url'] and item['url'].startswith('https://'):
                reranked_results.append({
                    'id': idx0,
                    'url': item['url'],
                    'description': item['description'].replace('\n', ' ').strip()
                    })   # append id, url, description
                idx0 += 1
    return reranked_results


def w3m_google(query: str, num_results: int = 10, domain:str='at', filter:bool='True') -> list:
    
    search_url = build_goog_search_url(query, num_results)
    content = fetch_with_w3m(search_url)
#    print(result)
    #print(get_numof_qresults(content))
    urllist = process_google_search(content)
    # please print the result starting from "Heute " bis zu "Details & Prognosen"
#    print(from_start_to_end(result, "Heute", "Details & Prognosen"))
    # Find the start and end indices
    '''for idx, item in enumerate(urllist):
        if item:
            # Extract the URL and description if they exist
            url = item.get('url', '').strip()
            description = item.get('description', '').replace('\n', ' ').strip()

            # Print the id (which is the index), and the first 20 characters of URL and first 200 characters of description
            print(f"ID: {idx+1}\n\tURL: {url[:] if url else 'None'}\n\tDescription: {description[:] if description else 'None'}")'''
    
    return urllist