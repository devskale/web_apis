from w3m import fetch_with_w3m, get_numof_qresults, process_google_search, w3m_google, build_goog_search_url
from unittest import mock

def from_start_to_end(text, start_str, end_str):
    start = text.find(start_str)
    end = text.find(end_str)
    return text[start:end]


def printurllist(urllist):
    for idx, item in enumerate(urllist):
        if item:
            # Extract the URL and description if they exist
            url = item.get('url', '').strip()
            description = item.get('description', '').replace('\n', ' ').strip()

            # Print the id (which is the index), and the first 20 characters of URL and first 200 characters of description
            print(f"ID: {idx+1}\n\tURL: {url[:] if url else 'None'}\n\tDescription: {description[:] if description else 'None'}")


urls = [
    "https://wetter.orf.at/burgenland",
    "https://www.google.at/search?q=wetter+burgenland&num=20",
    "https://www.google.at/search?q=OpenAI+Strawberry&num=20",
    "https://www.google.de/search?q=OpenAI+Strawberry&num=20",
    "https://www.google.com/search?q=OpenAI+Strawberry&num=20&lr=lang_en",
    ]


if __name__ == "__main__":

    test1 = False
    if test1 == True:
        print("test1")
        search_url = build_goog_search_url("elon musk", 3)
        print('search url:', search_url)
        content = fetch_with_w3m(search_url)
        urllist = process_google_search(content)
        printurllist(urllist)

    test2 = False
    urllist = []
    if test2 == True:
        print("test2")
        urllist = w3m_google("Elon Musk", 3)
        print(urllist);
        print("test2 Results:")
        print("[")
        printurllist(urllist)

    test3 = True
    if test3 == True:
        print("test3")
        urllist = w3m_google("orf nehammer", 3)
        # print only the first urllst element
#        printurllist([urllist[0]]) # Wrap the first element in a list
        # get url from the first element
        url = urllist[0]['url']
        print("URL:", url)
        content = fetch_with_w3m(url, links=False)
        print(content)

exit()
