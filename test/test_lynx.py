from lynx import lynx_url
from unittest import mock

def from_start_to_end(text, start_str, end_str):
    start = text.find(start_str)
    end = text.find(end_str)
    return text[start:end]

urls = [
    "https://wetter.orf.at/burgenland",
    "https://www.google.at/search?q=wetter+burgenland",
    ]

if __name__ == "__main__":
    result = lynx_url(urls[1])
    print(result[:3000])
    # please print the result starting from "Heute " bis zu "Details & Prognosen"
#   print(from_start_to_end(result, "Heute", "Details & Prognosen"))
    # Find the start and end indices
