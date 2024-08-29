# echoing.py

import sys
import re

def remove_special_characters(input_text):
    # Regular expression to match only alphanumeric characters and spaces
    cleaned_text = re.sub(r'[^a-zA-Z0-9\s]', '', input_text)
    return cleaned_text

def main():
    if len(sys.argv) > 1:
        # Join the arguments to form the input string
        input_text = ' '.join(sys.argv[1:])
        # Remove special characters
        cleaned_text = remove_special_characters(input_text)
        print(cleaned_text)
    else:
        print("No input text provided.")

if __name__ == "__main__":
    main()