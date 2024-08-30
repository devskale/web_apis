from w3m import fetch_with_w3m
from unittest import mock

def from_start_to_end(text, start_str, end_str):
    start = text.find(start_str)
    end = text.find(end_str)
    return text[start:end]



if __name__ == "__main__":
    result = fetch_with_w3m("https://wetter.orf.at/burgenland")
    #print(result[1000:3000])
    # please print the result starting from "Heute " bis zu "Details & Prognosen"
    print(from_start_to_end(result, "Heute", "Details & Prognosen"))
    # Find the start and end indices
