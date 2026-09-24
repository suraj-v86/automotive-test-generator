###########################################
# 1. IMPORTS AND OPENAI CLIENT SETUP
###########################################

from openai import OpenAI
import os
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")


# Read the model name from the environment.

model = os.getenv("AI_MODEL", "gpt-5.6-luna")

# 2. SYSTEM PROMPT

system_prompt = """
                You are an automotive software testing assistant.

                First use check_requirement_quality, then use analyze_requirement, and only after those checks generate test cases.

                Analyze automotive software requirements and generate relevant test scenarios, including functional, negative, and edge-case tests.

                Generate an expected result for each test scenario.
                """

###################################
# 3. USER INPUT VALIDATION
###################################

# Define the maximum length allowed for an automotive requirement.
max_requirement_length = 1000

# Ask the user to enter an automotive software requirement.
requirement = input("Enter automotive requirement: ")

# Remove unnecessary spaces from the beginning and end.
clean_requirement = requirement.strip()

# Reject an empty requirement before sending it to the AI model.
if not clean_requirement:
    print("Requirement cannot be empty.")
    exit()

# Reject requirements that exceed the maximum allowed length.
if len(clean_requirement) > max_requirement_length:
    print("Requirement is too long. Maximum length is 1000 characters.")
    exit()

# ============================================================
# 4. SENSITIVE-DATA PROTECTION
# ============================================================

# Check whether the requirement contains common sensitive
# information such as passwords, API keys, tokens, or secrets.

def contains_sensitive_data(clean_requirement):
    if "password" in clean_requirement or "api_key" in clean_requirement or "token" in clean_requirement or "secret" in clean_requirement:
        return True
    return False

# Stop processing if sensitive information is detected.
if contains_sensitive_data(clean_requirement):  
    print("Sensitive information detected. Service blocked.") 
    exit()    

# ============================================================
# # 5. REQUIREMENT QUALITY CHECK TOOL    
# ============================================================

# Check whether the requirement follows some basic quality rules.
# This tool is executed by the application when requested by the AI.
def check_requirement_quality(requirement):
    # Define the minimum acceptable requirement length.
    minimum_length = 20

    # Store any quality issues found in the requirement.
    issues = []

    # Check whether the requirement is long enough.
    if len(requirement) < minimum_length:
        issues.append("Requirement is too short. Needs review")

    # Check whether the requirement uses the word "shall".
    if "shall" not in requirement.lower():
        issues.append("Requirement should use 'shall'")

    # If no issues were found, return a positive quality result.    
    if not issues:
        return "Requirement quality is good."

    # Return all detected issues when the requirement needs review.
    return "Requirement quality needs review: " + " OR ".join(issues)


# ============================================================
# 6. TOOL DEFINITIONS FOR THE AI MODEL
# ============================================================

# Define the tools that the AI model is allowed to request.

quality_tool = [
    {
        "type": "function",
        "name": "check_requirement_quality",
        "description": "Check the quality of the input given by the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirement": {
                    "type": "string"
                }
            },
            "required": ["requirement"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "analyze_requirement",
        "description": "Analyze the requirement sent by the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirement": {
                    "type": "string"
                }
            },
            "required": ["requirement"],
            "additionalProperties": False
        }
    }
]    

# ============================================================
# 7. REQUIREMENT ANALYSIS TOOL
# ============================================================

# Analyze the requirement and determine whether it appears
# testable based on simple application-defined rules.
def analyze_requirement(requirement):
    analysis = {
        "requirement": requirement,
        "length": len(requirement),
        "uses_shall": True if "shall" in requirement.lower() else False,
        "has_vague_terms": True if "fast" in requirement.lower() or "quickly" in requirement.lower() or "soon" in requirement.lower() or "normally" in requirement.lower() else False       
    }

    if analysis["uses_shall"] and not analysis["has_vague_terms"]:
        analysis["testability"] = "Good"
    else:
        analysis["testability"] = "Needs review"

    if analysis["testability"] == "Good":
        analysis["test_types"] = "Functional, Negative, Edge"   
    else:
        analysis["test_types"] = "Requirement Review"

    return analysis    

# ============================================================
# 8. TEST-CASE GENERATION AGENT
# ============================================================

def generate_test_cases(requirement):

    # Track the current stage of the agent workflow.
    # The agent must execute the tools in this order:
    #
    # check_requirement_quality
    #
    # analyze_requirement
    #
    # generate_test_cases    

    current_stage = "check_requirement_quality"

    # Build the initial conversation sent to the AI model.
    request_input = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": requirement
        }
    ] 

    # ========================================================
    # 9. STRUCTURED OUTPUT SCHEMA
    # ========================================================

    # Define the exact JSON structure expected from the model.
    # This ensures every generated test case contains the required field.

    test_case_schema = {
        "type": "object",
        "properties": {
            "test_cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string"
                        },
                        "type": {
                            "type": "string"
                        },
                        "steps": {
                            "type": "string"
                        },
                        "expected_result": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "id",
                        "type",
                        "steps",
                        "expected_result"
                    ],
                    "additionalProperties": False
                }
                
            }
        },
        "required": ["test_cases"],
        "additionalProperties": False
    }

#####################################
# 10. REUSABLE AGENT LOOP
####################################
    # Create the OpenAI client. 
    # The client uses the configured API credentials from the environment.

    client = OpenAI(timeout=30.0)

    MAX_ITERATIONS = 5

    iteration = 0

    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0



# Continue interacting with the model until it produces the final structred test cases
    while True:

        iteration += 1

        if iteration == MAX_ITERATIONS - 1:
            logging.warning("Agent is approaching the maximum iteration limit.")

        if iteration > MAX_ITERATIONS:
            logging.error("Maximum agent iterations exceeded.")
            exit()

        logging.info("Sending request to AI service...")

        for retry in range(3):
            try:
                response = client.responses.create(
                    model=model,
                    input=request_input,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "automotive_test_cases",
                            "strict": True,
                            "schema": test_case_schema
                        }
                    },
                    tools=quality_tool
                )                
                
            except Exception:
                logging.exception("Unable to communicate with the AI service.")

                if retry == 2:
                    logging.error("Maximum API retry attempts exceeded.")
                    exit()

                logging.warning("Retrying API request after %s seconds.", 2 * 2 ** retry)
                time.sleep(2 * 2 ** retry)    


        logging.info("Response received from AI service.")
        logging.info("Successful API request")

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
        total_tokens += response.usage.total_tokens  

        logging.info("API call %s input tokens: %s", iteration, response.usage.input_tokens)
        logging.info("API call %s output tokens: %s", iteration, response.usage.output_tokens)
        logging.info("API call %s total tokens: %s", iteration, response.usage.total_tokens)

        # Map tool names to the Python functions that actually
        # execute those tools.

        tool_functions = {
            "check_requirement_quality": check_requirement_quality,
            "analyze_requirement": analyze_requirement
        }

        
        # ====================================================
        # 11. DETECT TOOL CALLS
        # ====================================================

        # Extract all function calls requested by the model.
        tool_calls = []

        # Display the tools requested by the model for debugging
        # and to make the agent workflow visible.
        for item in response.output:
            if item.type == "function_call":
                tool_calls.append(item)

        # If no tool calls were requested, the model has finished
        # the workflow and should have returned the final JSON.
        num_of_tools = len(tool_calls)

        logging.debug("Number of tools requested: %s", num_of_tools)

        if num_of_tools == 0:

            try:
                result = json.loads(response.output_text)
            except json.JSONDecodeError as e:
                logging.error("Invalid JSON response received from the AI service.")
                logging.error("Error: %s", e)
                exit()

            return result, total_input_tokens, total_output_tokens, total_tokens

            

        # Store the results that will be sent back to the model.
        tool_outputs = []

        ###################################################
        # 12. TOOL SAFETY AND EXECUTION
        ##################################################

        # Execute each requested tool only if:
        # 1. The tool is registered.
        # 2. It is the correct tool for the current workflow stage.

        for tool_call in tool_calls:
            logging.info("Tool requested: %s", tool_call.name)
            # Check whether the requested tool is known.
            if tool_call.name in tool_functions:
                # Enforce the required tool execution order.
                if tool_call.name == current_stage:

                    # Get the Python function associated with the tool.
                    function = tool_functions[tool_call.name]
                    # Convert the tool arguments from JSON text into a Python dictionary.
                    try:
                        arguments = json.loads(tool_call.arguments)
                    except json.JSONDecodeError as e:
                        logging.error("Invalid tool arguments received.")
                        logging.error("Error: %s", e)
                        exit()
                    # Execute the Python function.
                    try:
                        result = function(**arguments)
                        logging.info("Tool execution completed: %s", tool_call.name)
                    except Exception:
                        logging.exception("Tool execution failed.")
                        exit()

                    # Move to the next stage after successful execution.
                    if current_stage == "check_requirement_quality":
                        current_stage = "analyze_requirement"

                    elif current_stage == "analyze_requirement":
                        current_stage = "generate_test_cases"    
                    else:
                    # Stop if the model requests a tool that does
                    # not match the expected workflow stage.
                        print("Wrong stage: ", current_stage)
                        exit()
                else:
                # Stop if the model requests a tool that the
                # application has not registered.
                    print("Unknown tool requested: ", tool_call.name)
                    exit()

            # Build the tool result that will be returned to the model.
            # call_id connects the result to the original tool call.
                tool_output = {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(result)
                }
                tool_outputs.append(tool_output)

        # Add the model response and tool results to the conversation
        # so the model has the information needed for the next step.
            conversation_with_tools = [*request_input, *response.output, *tool_outputs]

            request_input = conversation_with_tools   

# ============================================================
# 13. GENERATE TEST CASES
# ============================================================

# Start the AI testing workflow using the validated requirement.
generated_tests, total_input_tokens, total_output_tokens, total_tokens = generate_test_cases(clean_requirement)

# ============================================================
# 14. APPLICATION-SIDE TEST-CASE VALIDATION
# ============================================================

def validate_test_cases(test_cases):
    # Make sure the top-level test_cases field exists.
    if not "test_cases" in test_cases:
        return False
    
    # Make sure test_cases is represented as a list.
    if not isinstance(test_cases["test_cases"], list):
        return False
    
    # Reject an empty list of test cases.
    if len(test_cases["test_cases"]) == 0:
        return False    

    # Store IDs that have already been encountered.
    # A set makes duplicate detection straightforward.
    seen_ids = set()

    # Define the accepted base test categories.
    allowed_types = {"Functional", "Negative", "Edge", "Boundary"}

    # Validate every generated test case individually.
    for test_case in test_cases["test_cases"]:          

        # Every test case must be represented as a dictionary.
        if not isinstance(test_case, dict):
            return False
        # Make sure all required fields are present.
        if not ("id" in test_case and "type" in test_case and "steps" in test_case and "expected_result" in test_case):
            return False 

        # Extract the base test type.
        # For example:
        # "Functional - Normal Operation" → "Functional"
        test_type = test_case["type"].split(" - ")[0]

        # Normalize variations such as "Edge Case" to "Edge".
        if test_type.startswith("Edge"):
            test_type = "Edge"

        # Reject test types that are not supported by the application.
        if test_type not in allowed_types:
            return False

        # Make sure all required fields contain meaningful values.        
        if test_case["id"].strip() == "" or test_case["type"].strip() == "" or test_case["steps"].strip() == "" or test_case["expected_result"].strip() == "":
            return False 

        # Extract and clean the test-case ID.  
        test_id = test_case["id"].strip() 

        # Reject duplicate test-case IDs. 
        if test_id in seen_ids:
            return False
        # Remember this ID for future duplicate checks.
        seen_ids.add(test_id)  
    # All validation checks passed.           
    return True        


# ============================================================
# 15. VALIDATE GENERATED TEST CASES
# ============================================================

is_valid = validate_test_cases(generated_tests)

if is_valid == True:
    print("Test cases are valid.")
else:
    print("Test cases are invalid.")
    exit()

logging.info("Total input tokens: %s", total_input_tokens)
logging.info("Total output tokens: %s", total_output_tokens)
logging.info("Total tokens:  %s", total_tokens) 

with open("generated_test_cases.json", "w") as file:
    json.dump(generated_tests, file, indent=4)


# ============================================================
# 16. DISPLAY GENERATED TEST CASES  
# ============================================================  

total_test_cases = 0
functional = 0
negative = 0
edge = 0
boundary = 0

unsupported_keywords = ["low", "arbitration", "concurrent"]

visual_warning_requirement = "visual warning"

automatic_braking_requirement = "automatically apply the brakes"

visual_warning_covered = False
automatic_braking_covered = False

visual_warning_cases = []
automatic_braking_cases = []

for test_case in generated_tests["test_cases"]:
    requirement_supported = True
    for word in unsupported_keywords:
        if word in test_case["type"].lower() or word in test_case["steps"].lower() or word in test_case["expected_result"].lower():
            requirement_supported = False

    print(test_case["id"], requirement_supported)

    test_case_text = test_case[ "type" ] + " " + test_case[ "steps" ] + " " + test_case[ "expected_result" ]

    expected = test_case["expected_result"].lower()

    # Visual warning coverage
    if (
        "visual warning" in expected
        and "no visual warning" not in expected
        and "does not issue" not in expected
    ):
        visual_warning_covered = True

        visual_warning_cases.append(test_case["id"])

    # Automatic braking positive coverage
    braking_terms = [
        "automatically applies the brakes",
        "applies automatic braking",
        "braking is activated",
        "brakes are applied",
        "braking intervention is initiated"
    ]

    if any(term in expected for term in braking_terms):
        automatic_braking_covered = True
        automatic_braking_cases.append(test_case["id"])


    total_test_cases += 1
    if test_case["type"].lower().startswith("functional"):
        functional += 1
    elif test_case["type"].lower().startswith("negative"):
        negative += 1
    elif test_case["type"].lower().startswith("edge"):
        edge += 1
    elif test_case["type"].lower().startswith("boundary"):
        boundary += 1

    print("-" * 50)
    print("Test case", test_case["id"])
    print("-" * 50)
    print("Type", test_case["type"])
    print("-" * 50)
    print("Steps", test_case["steps"])
    print("-" * 50)
    print("Expected Result", test_case["expected_result"])

print("\nTotal Case Summary")    
print("-" * 30)

print("Visual warning covered:", visual_warning_covered)
print("Automatic braking covered:", automatic_braking_covered)
print("Visual warning cases:", visual_warning_cases)
print("Automatic braking cases:", automatic_braking_cases)
print("Total test cases: ", total_test_cases)
print("Functional : ", functional)
print("Negative: ", negative)
print("Edge: ", edge)
print("Boundary: ", boundary)
