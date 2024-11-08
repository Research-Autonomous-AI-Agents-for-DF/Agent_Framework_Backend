import autogen
from typing import Dict, List
from autogen import Agent, GroupChat, GroupChatManager, UserProxyAgent, AssistantAgent
from autogen.coding import DockerCommandLineCodeExecutor

# Define the LLM configuration
llm_config = {
    "config_list": [
        {
            "model": "Llama 3.1",
            "base_url": "http://localhost:1234/v1",
            "api_key": "Test1",
            "seed": 25,
            "timeout": 300
        },
        {
            "model": "codeQwen-model:latest",
            "api_key":"test",
            "base_url": "http://localhost:11434/v1",
            "seed":25,
        }
    ]
}
llm_config2 = {"model": "gemini-1.5-flash","api_key":"AIzaSyBdxdqpBwXfgkCDz0chX1Ell0auD_8fLUs","api_type":"google","seed":25}
executor = DockerCommandLineCodeExecutor(
    image="resistor52/sleuthkit:latest",  # Execute code using the given docker image name.
    timeout=40,  # Timeout for each code execution in seconds.
    work_dir="coding",  # Use the temporary directory to store the code files.
)

# Create Task Translation Agent
task_translation_agent = AssistantAgent(
    name="Task_Translation_Agent",
    system_message="""You are a methodical AI assistant specialized in decomposing complex tasks into smaller, manageable subtasks that can be executed sequentially.
Your responsibilities include:
    Task Analysis: For every given prompt, analyze it thoroughly and break it down into the simplest possible steps(subtasks) that can be handled one at a time.
    Step Sequencing: Ensure that the subtasks are ordered logically, such that each subtask provides the necessary context or data required for the next. Each subtask should be self-contained and clearly described.
    Input-Output Validation: Make sure each subtask has a clear expected input and output, so that you can verify if a subtask was completed successfully before proceeding to the next.
    Reevaluation: After receiving the output of a completed subtask, reassess the situation if necessary and refine or adjust the remaining subtasks accordingly.
    Completion: Once all subtasks are successfully completed, review the final output, and declare the task as finished.
    If there is a subtask that includes coding, give me that subtask. You don't need to give me the code or what I should use to excecute. I will decide what to use and write the code myself. I will excecute and give you the results. Remember to only give me one subask at a time instead of providing the list of all subtasks. If the task requires an input from a previous task, give me that input as well. Do not provide any other text content outside the template.

Reply 'TASK COMPLETED' when the entire task list is fully broken down and executed.
""",
    llm_config=llm_config2,
)

# Create Coder Agent
coder_agent = AssistantAgent(
    name="Coder_Writer_Agent",
    llm_config=llm_config,
    code_execution_config=False,
    human_input_mode="ALWAYS",
    system_message=r"""Solve tasks using your coding and language skills.Remember these sleuthkit shell commands in tsk4 to solve tasks that involve bash commands.  Commands are 
    blkcalc - Converts between unallocated disk unit numbers and regular disk unit numbers.
    blkcat - Display the contents of file system data unit in a disk image.
    blkls - List or output file system data units.
    blkstat - Display details of a file system data unit (i.e. block or sector).
    fcat - Output the contents of a file based on its name.
    ffind - Finds the name of the file or directory using a given inode.
    fiwalk - print the filesystem statistics and exit.
    fls - List file and directory names in a disk image.
    fsstat - Display general details of a file system.
    hfind - Lookup a hash value in a hash database.
    icat - Output the contents of a file based on its inode number.
    ifind - Find the meta-data structure that has allocated a given disk unit or file name.
    ils - List inode information.
    img_cat - Output contents of an image file.
    img_stat - Display details of an image file.
    istat - Display details of a meta-data structure (i.e. inode).
    jcat - Show the contents of a block in the file system journal.
    jls - List the contents of a file system journal.
    jpeg_extract - jpeg extractor.
    mactime - Create an ASCII time line of file activity.
    mmcat - Output the contents of a partition to stdout.
    mmls - Display the partition layout of a volume system (partition tables).
    mmstat - Display details about the volume system (partition tables).
    sigfind - Find a binary signature in a file.
    sorter - Sort files in an image into categories based on file type.
    srch_strings - Display printable strings in files.
    tsk_comparedir - compare the contents of a directory with the contents of an image or local device.
    tsk_gettimes - Collect MAC times from a disk image into a body file.
    tsk_loaddb - populate a SQLite database with metadata from a disk image.
    tsk_recover - Export files from an image into a local directory.

In the following cases, suggest python code (in a python coding block) or shell script (in a sh coding block) for the user to execute.
    1. When you need to collect info, use the code to output the info you need, for example, browse or search the web, download/read a file, print the content of a webpage or a file, get the current date/time, check the operating system. After sufficient info is printed and the task is ready to be solved based on your language skill, you can solve the task by yourself.
    2. When you need to perform some task with code, use the code to perform the task and output the result. Finish the task smartly.
When using code, you must indicate the script type in the code block. The user cannot provide any other feedback or perform any other action beyond executing the code you suggest. The user can't modify your code. So do not suggest incomplete code which requires users to modify. Don't use a code block if it's not intended to be executed by the user.
If you want the user to save the code in a file before executing it, put # filename: <filename> inside the code block as the first line. Don't include multiple code blocks in one response. Do not ask users to copy and paste the result. Instead, use 'print' function for the output when relevant. Check the execution result returned by the user.
If the result indicates there is an error, fix the error and output the code again. Suggest the full code instead of partial code or code changes. If the error can't be fixed or if the task is not solved even after the code is executed successfully, analyze the problem, revisit your assumption, collect additional info you need, and think of a different approach to try.
When you find an answer, verify the answer carefully. Include verifiable evidence in your response if possible.
Reply "TERMINATE" in the end when everything is done.
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
        return coder_agent

    elif last_speaker is coder_agent:
        # After Coder Agent, human input is required
        if "Human" in messages[-1]["content"]:
            return "manual"  # Switch to manual mode for human input
        return code_executor_agent

    elif last_speaker is code_executor_agent:

        if "execution failed" in messages[-1]["content"] or "failed" in messages[-1]["content"] or "change" in \
                messages[-1]["content"]:
            print("It works")
            return coder_agent
        elif "success" in messages[-1]["content"]:
            return task_translation_agent
        return reporter_agent

    elif last_speaker is reporter_agent:
        return "manual"  # End the chat, switch to manual for final review

    else:
        return "random"  # Default fallback


# Create the GroupChat with agents
groupchat = GroupChat(
    agents=[task_translation_agent, coder_agent, code_executor_agent, reporter_agent],
    messages=[],
    max_round=20,
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
    manager, message=r"""Task: Recover a file from the emtied recycle bin.
    Disk Location: ./TestImages/dfr-01-recycle-ntfs.dd
    How to Analyze: File system forensics using The Sleuth Kit commandline tools."""
)

# Continue with the process flow and handle human input as needed
