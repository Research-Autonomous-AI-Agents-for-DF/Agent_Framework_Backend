import re
import requests

from typing_extensions import Annotated
from bs4 import BeautifulSoup
from autogen.coding import DockerCommandLineCodeExecutor
    
    # Create executor if not already defined
if 'executor' not in globals():
    executor = DockerCommandLineCodeExecutor(
        image="resistor52/sleuthkit:latest",
        timeout=40,
        work_dir="coding",
    )
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
def getImageInfo(image_location:Annotated[str, "Image Location"]) -> str:
    """Identify the partition offsets using mmls and return the results"""
    codeMessage = f"""```sh
                    mmls {image_location}
                    ```"""
    raw_output = getCodeOutput(codeMessage)
    return raw_output
    
def identifyFileSystem(image_location: Annotated[str, "Image Location"], 
                      offset: Annotated[str, "Partition Offset"]) -> str:
    """Identify file system type using fsstat and return the results"""
    codeMessage = f"""```sh
                    fsstat -o {offset} {image_location}
                    ```"""
    output = getCodeOutput(codeMessage)
    return output

def listDeletedFiles(image_location: Annotated[str, "Image Location"], 
                    offset: Annotated[str, "Partition Offset"]) -> str:
    """List deleted files using fls and return the results"""
    codeMessage = f"""```sh
                    fls -d -o {offset} {image_location}
                    ```"""
    output = getCodeOutput(codeMessage)
    return output

def recoverFile(image_location: Annotated[str, "Image Location"], 
               offset: Annotated[str, "Partition Offset"],
               inode: Annotated[str, "Inode Number"],
               output_file: Annotated[str, "Output File Name"]) -> str:
    """Recover a file using icat based on inode number"""
    codeMessage = f"""```sh
                    icat -o {offset} {image_location} {inode} > {output_file}
                    ```"""
    output = getCodeOutput(codeMessage)
    return f"File recovered to {output_file}"

def getCodeOutput(codeMessage):
    code_blocks = executor.code_extractor.extract_code_blocks(message=codeMessage)
    code_output = executor.execute_code_blocks(code_blocks=code_blocks)
    return code_output.output