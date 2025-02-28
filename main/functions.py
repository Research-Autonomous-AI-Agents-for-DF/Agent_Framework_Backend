import re
import requests

from typing_extensions import Annotated
from bs4 import BeautifulSoup

def get_tool_documentation(commandName:Annotated[str, "Sleuth Kit Command Line Tool Name"]) -> str:
    url = f"http://www.sleuthkit.org/sleuthkit/man/{commandName}.html"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    body_content = soup.find('body')
    return f"{body_content}"
def parse_mmls_output(output):
    result = {
        "partition_table_type": "",
        "offset_sector": 0,
        "unit_size": 0,
        "partitions": []
    }
    
    lines = output.strip().split('\n')
    
    # Extract partition table type
    if lines and "Partition Table" in lines[0]:
        result["partition_table_type"] = lines[0].strip()
    
    # Extract offset sector
    offset_match = re.search(r"Offset Sector:\s+(\d+)", output)
    if offset_match:
        result["offset_sector"] = int(offset_match.group(1))
    
    # Extract unit size
    unit_match = re.search(r"Units are in (\d+)-byte sectors", output)
    if unit_match:
        result["unit_size"] = int(unit_match.group(1))
    
    # Find the line with column headers
    header_index = -1
    for i, line in enumerate(lines):
        if "Slot" in line and "Start" in line and "End" in line:
            header_index = i
            break
    
    if header_index >= 0:
        # Process partition entries
        for line in lines[header_index + 1:]:
            # Skip empty lines
            if not line.strip():
                continue
            
            # Use regex to handle various spacing in the output
            parts = re.split(r'\s+', line.strip())
            if len(parts) >= 5:
                # Format may vary, but we expect at least 5 columns
                slot = parts[0] + parts[1]
                start = int(parts[2]) if parts[2].isdigit() else parts[2]
                end = int(parts[3]) if parts[3].isdigit() else parts[3]
                length = int(parts[4]) if parts[4].isdigit() else parts[4]
                description = " ".join(parts[5:])
                
                partition = {
                    "slot": slot,
                    "start": start,
                    "end": end,
                    "length": length,
                    "description": description
                }
                
                result["partitions"].append(partition)
    
    return result