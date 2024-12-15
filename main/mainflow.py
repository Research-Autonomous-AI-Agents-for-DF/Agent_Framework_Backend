import autogen
from typing import Dict, List
from autogen import Agent, GroupChat, GroupChatManager, UserProxyAgent, AssistantAgent
from autogen.coding import DockerCommandLineCodeExecutor
import os
from dotenv import load_dotenv

# Define the LLM configuration
# Load environment variables from .env file
load_dotenv()
load_dotenv("../.env.local", override=True)

llm_config = {
    "config_list": [
        {
            "model": os.getenv("LLM_MODEL"),
            "base_url": os.getenv("LLM_BASE_URL"),
            "api_key": os.getenv("LLM_API_KEY"),
            "seed": int(os.getenv("LLM_SEED", 25)),  # Default seed if not set
            "timeout": int(os.getenv("LLM_TIMEOUT", 300))  # Default timeout if not set
        }
    ]
}
executor = DockerCommandLineCodeExecutor(
    image="resistor52/sleuthkit:latest",  # Execute code using the given docker image name.
    timeout=40,  # Timeout for each code execution in seconds.
    work_dir="coding",  # Use the temporary directory to store the code files.
)

# Create Task Translation Agent
task_translation_agent = AssistantAgent(
    name="Task_Translation_Agent",
    system_message="""You are an expert in SleuthKit commands. For each task, break it into smaller actionable 
    subtasks.Output only one subtask at a time using the provided command list:

Commands are:
- blkcalc: Converts between unallocated disk unit numbers and regular disk unit numbers.
- blkcat: Display the contents of a file system data unit in a disk image.
- blkls: List or output file system data units.
- blkstat: Display details of a file system data unit (i.e., block or sector).
- fcat: Output the contents of a file based on its name.
- ffind: Finds the name of the file or directory using a given inode.
- fiwalk: Print the filesystem statistics and exit.
- fls: List file and directory names in a disk image.
- fsstat: Display general details of a file system.
- hfind: Lookup a hash value in a hash database.
- icat: Output the contents of a file based on its inode number.
- ifind: Find the meta-data structure that has allocated a given disk unit or file name.
- ils: List inode information.
- img_cat: Output contents of an image file.
- img_stat: Display details of an image file.
- istat: Display details of a meta-data structure (i.e., inode).
- jcat: Show the contents of a block in the file system journal.
- jls: List the contents of a file system journal.
- jpeg_extract: JPEG extractor.
- mactime: Create an ASCII timeline of file activity.
- mmcat: Output the contents of a partition to stdout.
- mmls: Display the partition layout of a volume system (partition tables).
- mmstat: Display details about the volume system (partition tables).
- sigfind: Find a binary signature in a file.
- sorter: Sort files in an image into categories based on file type.
- srch_strings: Display printable strings in files.
- tsk_comparedir: Compare the contents of a directory with the contents of an image or local device.
- tsk_gettimes: Collect MAC times from a disk image into a body file.
- tsk_loaddb: Populate a SQLite database with metadata from a disk image.
- tsk_recover: Export files from an image into a local directory.

**Output only the one Step at a time.

""",
    llm_config=llm_config,
)

# Create Coder Agent
coder_agent = AssistantAgent(
    name="Coder_Writer_Agent",
    llm_config=llm_config,
    code_execution_config=False,
    human_input_mode="ALWAYS",
    system_message=r"""You are a helpful AI assistant.
Solve tasks using your coding and language skills.
In the following cases, suggest python code (in a python coding block) or shell script (in a sh coding block) for the user to execute.
    1. When you need to collect info, use the code to output the info you need, for example, browse or search the web, download/read a file, print the content of a webpage or a file, get the current date/time, check the operating system. After sufficient info is printed and the task is ready to be solved based on your language skill, you can solve the task by yourself.
    2. When you need to perform some task with code, use the code to perform the task and output the result. Finish the task smartly.
Solve the task step by step if you need to. If a plan is not provided, explain your plan first. Be clear which step uses code, and which step uses your language skill.
When using code, you must indicate the script type in the code block. The user cannot provide any other feedback or perform any other action beyond executing the code you suggest. The user can't modify your code. So do not suggest incomplete code which requires users to modify. Don't use a code block if it's not intended to be executed by the user.
If you want the user to save the code in a file before executing it, put # filename: <filename> inside the code block as the first line. Don't include multiple code blocks in one response. Do not ask users to copy and paste the result. Instead, use 'print' function for the output when relevant. Check the execution result returned by the user.
If the result indicates there is an error, fix the error and output the code again. Suggest the full code instead of partial code or code changes. If the error can't be fixed or if the task is not solved even after the code is executed successfully, analyze the problem, revisit your assumption, collect additional info you need, and think of a different approach to try.
When you find an answer, verify the answer carefully. Include verifiable evidence in your response if possible.
Reply "TERMINATE" in the end when everything is done.
If you are generating a shell script, dont have any blank lines as it gets interpreted as \r in the terminal
"""
)

# Create Code Executor Agent
code_executor_agent = UserProxyAgent(
    name="Code_Executor_Agent",
    code_execution_config={"executor": executor},
    default_auto_reply=
    "Please continue. If everything is done, reply 'TERMINATE'.",
)

# Create Reporter Agent
reporter_agent = AssistantAgent(
    name="Reporter_Agent",
    system_message="""
    You are a digital forensics expert responsible for generating comprehensive and accurate forensic reports. Your task is to summarize the findings, methodologies, and conclusions derived from the analysis of disk images and related data. The report should be structured as follows:
    
    1. **Executive Summary**: Provide a brief overview of the investigation, including the purpose, scope, and key findings.
    
    2. **Methodology**: Detail the tools, techniques, and commands used in the analysis, including any relevant parameters and configurations.
    
    3. **Findings**: Summarize the results of the analysis, including any files or data recovered, evidence of tampering or deletion, and other relevant artifacts. Include specific command outputs where necessary.
    
    4. **Analysis**: Provide a detailed interpretation of the findings, explaining the significance of the recovered data in the context of the investigation.
    
    5. **Conclusion**: Offer a summary of the conclusions drawn from the analysis, including any recommendations for further investigation or actions.
    
    6. **Appendices**: Include any additional materials, such as full command outputs, logs, or scripts, that support the findings and conclusions.

    Ensure that the report is clear, concise, and free of any technical jargon that might confuse a non-expert reader. Include timestamps and references to specific data sources where applicable. Aim for accuracy, clarity, and thoroughness in every section of the report.
    """,
    llm_config=llm_config,

)


# Create a custom speaker selection function
def custom_speaker_selection_func(last_speaker: Agent, groupchat: GroupChat):
    messages = groupchat.messages

    if len(messages) <= 1:
        return task_translation_agent

    if last_speaker is task_translation_agent:
        # Generate one task at a time, then pass to Coder Agent
        return coder_agent

    elif last_speaker is coder_agent:
        # After Coder Agent, pass the task to Code Executor Agent
        return code_executor_agent

    elif last_speaker is code_executor_agent:
        # Check if execution was successful or failed
        if "execution failed" in messages[-1]["content"] or "failed" in messages[-1]["content"] or "change" in messages[-1]["content"] or "Error" in messages[-1]["content"]:
            return coder_agent  # Retry with the Coder Agent if failed

        # If successful, go back to Task Translation Agent for the next task
        if "execution successful" in messages[-1]["content"] or "success" in messages[-1]["content"] or "succeed" in messages[-1]["content"]:
            return task_translation_agent

    elif last_speaker is reporter_agent:
        # Once all tasks are completed, switch to manual mode for final review
        return "manual"

    else:
        # Default fallback
        return "random"


# Create the GroupChat with agents
groupchat = GroupChat(
    agents=[task_translation_agent, coder_agent, code_executor_agent, reporter_agent],
    messages=[],
    max_round=40,
    speaker_selection_method=custom_speaker_selection_func,
)

# Initialize GroupChatManager





manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)

# Start the conversation by sending a task to the Task Translation Agent
user_proxy = UserProxyAgent(
    name="Admin",
    system_message="A human admin. Review the outputs from the agents.",
    code_execution_config=False,

)

user_proxy.initiate_chat(
    manager, message="Examine the disk image in the of the current working directory named "
                     "'dfr-01-ntfs.dd' using the sleuthkit commands. Use the tsk 4 and tsk 3 command lists and come up "
                     "with a list of deleted file names. Store them in file named 'deleted_files.txt'."
)

# Continue with the process flow and handle human input as needed
