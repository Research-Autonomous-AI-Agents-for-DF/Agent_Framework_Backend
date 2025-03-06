import os

from autogen import UserProxyAgent, register_function
from autogen.coding import DockerCommandLineCodeExecutor
from dotenv import load_dotenv
from agents.output_interpreter import OutputInterpreter
from agents.workflow_coordinator import WorkflowCoordinator
from functions import getImageInfo, identifyFileSystem, listDeletedFiles, recoverFile

# Load environment variables from .env file
load_dotenv()
load_dotenv("./.env.local", override=True)

config_list = []

for model in os.getenv("LLM_MODEL").split(","):
    config_list.append(
        {
            "model": model,
            "client_host": os.getenv("LLM_BASE_URL"),
            "api_type": "ollama",
            "timeout": int(os.getenv("LLM_TIMEOUT", 500)),  # Default timeout if not set
            "temperature": 0.0,
            "stream": True
        }
    )
llm_config = {
    "config_list": config_list,
}

executor = DockerCommandLineCodeExecutor(
    image="resistor52/sleuthkit:latest",  # Execute code using the given docker image name.
    timeout=40,  # Timeout for each code execution in seconds.
    work_dir="coding",  # Use the temporary directory to store the code files.
)
# Create executor if not already defined
if 'executor' not in globals():
    globals()['executor'] = executor


workflow_coordinator = WorkflowCoordinator(llm_config=config_list[1]).get_agent()
output_interpreter = OutputInterpreter(llm_config=config_list[1]).get_agent()
toolcall_user_proxy = UserProxyAgent(
    name="Toolcall_User_Proxy",
    code_execution_config=False,
    default_auto_reply="Please continue. If everything is done, reply 'TERMINATE'.",
)
workflow_user_proxy = UserProxyAgent(
    name="Workflow_User_Proxy",
    code_execution_config=False,
    default_auto_reply="Please continue. If everything is done, reply 'TERMINATE'.",
)
def tool_call_message(recipient, messages, sender, config):
    print("Sending to for tool call...", "yellow")
    return f"Please interpret the following context and call the relevant tool:\n\n {recipient.chat_messages_for_summary(sender)[-1]['content']}"
# Register nested chat between output interpreter and toolcall proxy
workflow_user_proxy.register_nested_chats(
    [
        {
            "sender": toolcall_user_proxy,
            "recipient": output_interpreter,
            "message": tool_call_message,
            "max_turns": 2,
            "summary_method": "last_msg",
        }
    ],
    trigger=workflow_coordinator
)

register_function(
    getImageInfo,
    caller=output_interpreter,
    executor=toolcall_user_proxy,
    name="getImageInfo",
    description="Get the partition information of the disk image.",
)
register_function(
    identifyFileSystem,
    caller=output_interpreter,
    executor=toolcall_user_proxy,
    name="identifyFileSystem",
    description="Identify the file system type of a partition.",
)

register_function(
    listDeletedFiles,
    caller=output_interpreter,
    executor=toolcall_user_proxy,
    name="listDeletedFiles",
    description="List deleted files in a partition.",
)

register_function(
    recoverFile,
    caller=output_interpreter,
    executor=toolcall_user_proxy,
    name="recoverFile",
    description="Recover a file based on its inode number.",
)
# Start the conversation by sending a task to the Task Translation Agent
workflow_user_proxy.initiate_chat(
    workflow_coordinator, message="""Initial user message:
Examine the deleted files in the disk image using the sleuthkit command line tools. Come up with the list of files, the partition they are located and assign a priority to each.    
image_location: ./dataset/test_image_2.dd"""
)