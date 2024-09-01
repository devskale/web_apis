from w3m import fetch_with_w3m, get_numof_qresults, process_google_search, w3m_google
from unittest import mock

def from_start_to_end(text, start_str, end_str):
    start = text.find(start_str)
    end = text.find(end_str)
    return text[start:end]

urls = [
    "https://wetter.orf.at/burgenland",
    "https://www.google.at/search?q=wetter+burgenland&num=20",
    "https://www.google.at/search?q=OpenAI+Strawberry&num=20",
    "https://www.google.de/search?q=OpenAI+Strawberry&num=20",
    "https://www.google.com/search?q=OpenAI+Strawberry&num=20&lr=lang_en",
    ]


if __name__ == "__main__":
    '''
        content = fetch_with_w3m(urls[3])
    #    print(result)
        print(get_numof_qresults(content))
        urllist = process_google_search(content)
        # please print the result starting from "Heute " bis zu "Details & Prognosen"
    #    print(from_start_to_end(result, "Heute", "Details & Prognosen"))
        # Find the start and end indices
        for idx, item in enumerate(urllist):
            if item:
                # Extract the URL and description if they exist
                url = item.get('url', '').strip()
                description = item.get('description', '').replace('\n', ' ').strip()

                # Print the id (which is the index), and the first 20 characters of URL and first 200 characters of description
                print(f"ID: {idx+1}\n\tURL: {url[:] if url else 'None'}\n\tDescription: {description[:] if description else 'None'}")
    '''
    urllist = w3m_google("OpenAI Strawberry", 10)
    for url in urllist:
        print(url)
    exit()
    for idx, item in enumerate(urllist):
        if item:
            # Extract the URL and description if they exist
            url = item.get('url', '').strip()
            description = item.get('description', '').replace('\n', ' ').strip()

            # Print the id (which is the index), and the first 20 characters of URL and first 200 characters of description
            print(f"ID: {idx+1}\n\tURL: {url[:] if url else 'None'}\n\tDescription: {description[:] if description else 'None'}")
