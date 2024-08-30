from goog import goog_search


if __name__ == "__main__":
    result = goog_search("OpenAi Strawberry", num_results=4)
    #print(result[1000:3000])
    # please print the result starting from "Heute " bis zu "Details & Prognosen"
    print(result)
    # Find the start and end indices
