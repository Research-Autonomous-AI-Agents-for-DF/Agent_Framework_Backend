import requests

from typing_extensions import Annotated
from bs4 import BeautifulSoup

def get_tool_documentation(commandName:Annotated[str, "Sleuth Kit Command Line Tool Name"]) -> str:
    url = f"http://www.sleuthkit.org/sleuthkit/man/{commandName}.html"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    body_content = soup.find('body')
    return f"{body_content}"