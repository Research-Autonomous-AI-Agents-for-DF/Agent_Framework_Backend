import requests

from typing_extensions import Annotated
from bs4 import BeautifulSoup

def get_tool_documentation(commandName:Annotated[str, "Sleuth Kit Command Line Tool Name"]) -> str:
    url = f"http://www.sleuthkit.org/sleuthkit/man/{commandName}.html"
    response = requests.get(url)
    if response.status_code == 404:
        return "Tool documentation not found"
    soup = BeautifulSoup(response.text, 'html.parser')
    body_content = soup.find('body')
    return body_content.text
def ask_human_expert(question:Annotated[str, "Question"]) -> str:
    print("Please answer the following question:")
    print(question)
    answer = input("Your answer: ")
    return answer