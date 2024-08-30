from ducknews import search_news, search_text, search_maps, search_translate

def test_search_news():
    print("Testing search_news...")
    results = search_news("OpenAI Strawberry")
    print(f"Results: {results}")
    print("\n")

def test_search_text():
    print("Testing search_text...")
    results = search_text("python programming")
    print(f"Results: {results}")
    print("\n")

def test_search_maps():
    print("Testing search_maps...")
    results = search_maps("restaurants", "New York")
    print(f"Results: {results}")
    print("\n")

def test_search_translate():
    print("Testing search_translate...")
    results = search_translate("Hello", "es")
    print(f"Results: {results}")
    print("\n")

if __name__ == "__main__":
    test_search_news()
#    test_search_text()
#    test_search_maps()
#    test_search_translate()