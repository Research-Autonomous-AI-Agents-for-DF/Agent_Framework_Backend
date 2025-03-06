from typing import Dict, Any, List
from autogen import AssistantAgent

class OutputInterpreter:
    def __init__(self, llm_config: Dict[str, Any]):
        self.interpreter_agent = AssistantAgent(
            name="Output_Interpreter",
            system_message="""You are an output interpreter for digital forensics tools.
Your role is to:
1. Call and process raw tool outputs into structured JSON format
2. Extract relevant information based on the tool and context
3. Format data consistently for downstream processing

For each tool output:
- Parse the raw text output
- Identify key information and data points
- Structure the data into appropriate JSON format
- Handle both single objects and arrays of objects
- Maintain consistent key naming conventions
- Validate the structured output

Example Formats:
Single piece of info:
{
    "key1": "value1",
    "key2": "value2"
}

Multiple pieces of same type:
[
    {
        "key1": "value1",
        "key2": "value2"
    },
    {
        "key1": "value3", 
        "key2": "value4"
    }
]

Some values are hex values of the form 0x123. For them just remove the 0x in front when converting to json or when calling a tool.
""",
            llm_config=llm_config
        )

    def get_agent(self):
        return self.interpreter_agent
