from typing import Dict, Any
from autogen import AssistantAgent

class WorkflowCoordinator:
    def __init__(self, llm_config: Dict[str, Any]):
        self.coordinator_agent = AssistantAgent(
            name="Workflow_Coordinator",
            system_message="""You are the workflow coordinator for a digital forensics investigation.
Your job is to manage the progression through a structured forensic workflow:

1. Analyze Disk Image Structure (Output: Starting offsets for partitions or 0 if no partition)
2. Identify File System Type (Input: start offset for the partition, Output: File system type for each partition)
3. Discover Deleted Files (Input: file system type and Offset to partition, Output: file names and inode numbers)
4. Execute File Recovery (Input: file system type, offset and inode numbers, Output: recovered file)

For each step:
1. Determine which step in the workflow needs to be executed next
2. Track what information has been collected from previous steps
3. Format requests to the Task Translation Agent with precise instructions for the current workflow step
4. Store outputs from each step to pass to subsequent steps
5. Signal when the workflow is complete

Ensure that each step has the required inputs from previous steps before proceeding.
Keep track of all discovered information in a structured way.
Suggest from the following tools to call:
[getImageInfo, identifyFileSystem, listDeletedFiles, recoverFile]

Output format (only output one step at a time):
{{suggested tool}}
{{inputs for the tool}}
{{Needed information}}
""",
            llm_config=llm_config
        )

    def get_agent(self):
        return self.coordinator_agent