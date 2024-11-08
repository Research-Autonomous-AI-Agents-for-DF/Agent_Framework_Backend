# Agent_Framework_Backend

# Project Setup Guide

This guide provides detailed instructions on setting up the project, configuring environment files, and running the application.

## Table of Contents
- [Cloning the Repository](#cloning-the-repository)
- [Environment Configuration](#environment-configuration)
  - [Setting Up `.env.local`](#setting-up-envlocal)
- [Installing Dependencies](#installing-dependencies)
- [Running the Application](#running-the-application)

---

### Cloning the Repository

To get started, clone the repository from GitHub to your local machine. Run the following command in your terminal:

```bash
git clone https://github.com/Research-Autonomous-AI-Agents-for-DF/Agent_Framework_Backend.git
cd project-repository

```

## Environment Configuration

The project includes a `.env` file with common configuration placeholders. You only need to create a `.env.local` file in the root directory for sensitive configurations or overrides specific to your local environment.

### Setting Up `.env.local`

1. In the root directory, create a new file named `.env.local`.
2. Add your sensitive configurations (e.g., API keys) to this file. These values will override placeholders in `.env` and will not be tracked in version control.

   Here’s an example of what `.env.local` might look like:

```bash
# Sensitive configuration values for local setup
   LLM_MODEL="Llama 3.1"
   LLM_BASE_URL="http://localhost:1234/v1"
   LLM_API_KEY="lm-studio"
```
## Installing Dependencies

It’s recommended to use a virtual environment to manage dependencies for this project. Follow these steps:

1. **Create a virtual environment** (optional but recommended):

```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```
## Running the Application

With your environment set up and dependencies installed, you can start the application by running:

```bash
python mainflow.py
```