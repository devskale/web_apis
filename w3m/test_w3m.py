import pytest
from w3m import fetch_with_w3m
from unittest import mock


if __name__ == "__main__":
    result = fetch_with_w3m("https://www.orf.at")
    print(result)
