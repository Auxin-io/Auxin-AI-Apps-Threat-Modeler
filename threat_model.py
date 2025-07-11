import json
import requests
import base64
from anthropic import Anthropic
from mistralai import Mistral, UserMessage
from openai import OpenAI, AzureOpenAI
import streamlit as st
import re

from google import genai as google_genai 
from groq import Groq
from utils import process_groq_response, create_reasoning_system_prompt

# Function to convert JSON to Markdown for display.    
def json_to_markdown(threat_model, improvement_suggestions):
    markdown_output = "## Threat Model\n\n"
    
    # Start the markdown table with headers
    markdown_output += "| Threat Type | Scenario | Potential Impact |\n"
    markdown_output += "|-------------|----------|------------------|\n"
    
    # Fill the table rows with the threat model data
    for threat in threat_model:
        markdown_output += f"| {threat['Threat Type']} | {threat['Scenario']} | {threat['Potential Impact']} |\n"
    
    markdown_output += "\n\n## Improvement Suggestions\n\n"
    for suggestion in improvement_suggestions:
        markdown_output += f"- {suggestion}\n"
    
    return markdown_output

# Function to create a prompt for generating a threat model
def create_threat_model_prompt(app_type, authentication, internet_facing, sensitive_data, app_input):
    prompt = f"""
Assume the role of a cybersecurity expert with over 20 years of experience applying the STRIDE threat modeling methodology to develop detailed threat models for diverse software systems. Your job is to evaluate the given application description, code summary, and README content to identify specific security threats relevant to the application.
Pay particular attention to the README, as it often reveals crucial insights about the application's design, architecture, and potential security issues.
For each STRIDE category (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege), identify 3 to 4 realistic and relevant threat scenarios. Each scenario should describe a plausible way the threat could occur within the context of the specific application. Make sure your analysis reflects the actual information provided—tailor your responses accordingly.

Present your output in a JSON format with two main sections: "threat_model" and "improvement_suggestions".
Under "threat_model", include an array of threat objects. Each object should have the following keys:
1.) "Threat Type": the STRIDE category
2.) "Scenario": a realistic threat scenario based on the application
3.) "Potential Impact": the potential consequences if the threat is realized

Under "improvement_suggestions", list specific pieces of additional information the user could provide to improve the threat model’s accuracy and depth. Focus these suggestions on identifying current information gaps, such as:
1.)Missing architecture or component details
2.)Unclear user authentication processes
3.) Vague or missing data flow descriptions
4.) Lack of clarity on the technology stack
5.) Undefined system boundaries or trust levels
6.) Missing details about how sensitive data is managed

Avoid offering generic security advice—only highlight what specific additional information is needed to perform a more refined and accurate threat assessment.

APPLICATION TYPE: {app_type}
AUTHENTICATION METHODS: {authentication}
INTERNET FACING: {internet_facing}
SENSITIVE DATA: {sensitive_data}
CODE SUMMARY, README CONTENT, AND APPLICATION DESCRIPTION:
{app_input}

Example of expected JSON response format:
  
    {{
      "threat_model": [
        {{
          "Threat Type": "Spoofing",
          "Scenario": "Example Scenario 1",
          "Potential Impact": "Example Potential Impact 1"
        }},
        {{
          "Threat Type": "Spoofing",
          "Scenario": "Example Scenario 2",
          "Potential Impact": "Example Potential Impact 2"
        }},
        // ... more threats
      ],
      "improvement_suggestions": [
        "Please provide more details about the authentication flow between components to better analyze potential authentication bypass scenarios.",
        "Consider adding information about how sensitive data is stored and transmitted to enable more precise data exposure threat analysis.",
        // ... more suggestions for improving the threat model input
      ]
    }}
"""
    return prompt

def create_image_analysis_prompt():
    prompt = """
    You are a Senior Solution Architect tasked with explaining the following architecture diagram to 
    a Security Architect to support the threat modelling of the system.

    In order to complete this task you must:

      1. Analyse the diagram
      2. Explain the system architecture to the Security Architect. Your explanation should cover the key 
         components, their interactions, and any technologies used.
    
    Provide a direct explanation of the diagram in a clear, structured format, suitable for a professional 
    discussion.
    
    IMPORTANT INSTRUCTIONS:
     - Do not include any words before or after the explanation itself. For example, do not start your
    explanation with "The image shows..." or "The diagram shows..." just start explaining the key components
    and other relevant details.
     - Do not infer or speculate about information that is not visible in the diagram. Only provide information that can be
    directly determined from the diagram itself.
    """
    return prompt

# Function to get analyse uploaded architecture diagrams.
def get_image_analysis(api_key, model_name, prompt, base64_image):
    client = OpenAI(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                }
            ]
        }
    ]
    
    # If using o4-mini, use the structured system prompt approach
    if model_name == "o4-mini":
        system_prompt = create_reasoning_system_prompt(
            task_description="Analyze the provided architecture diagram and explain it to a Security Architect.",
            approach_description="""1. Carefully examine the diagram
2. Identify all components and their relationships
3. Note any technologies, protocols, or security measures shown
4. Create a clear, structured explanation with these sections:
   - Overall Architecture: Brief overview of the system
   - Key Components: List and explain each major component
   - Data Flow: How information moves through the system
   - Technologies Used: Identify technologies, frameworks, or platforms
   - Security Considerations: Note any visible security measures"""
        )
        # Insert system message at the beginning
        messages.insert(0, {"role": "system", "content": system_prompt})
        
        # Create completion with max_completion_tokens for reasoning models
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_completion_tokens=4000
            )
            return {
                "choices": [
                    {"message": {"content": response.choices[0].message.content}}
                ]
            }
        except Exception as e:
            return None
    else:
        # For standard models (gpt-4, etc.)
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=4000
            )
            return {
                "choices": [
                    {"message": {"content": response.choices[0].message.content}}
                ]
            }
        except Exception as e:
            return None

# Function to get image analysis using Azure OpenAI
def get_image_analysis_azure(api_endpoint, api_key, api_version, deployment_name, prompt, base64_image):
    client = AzureOpenAI(
        azure_endpoint=api_endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    response = client.chat.completions.create(
        model=deployment_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ],
            }
        ],
        max_tokens=4000,
    )

    return {
        "choices": [
            {"message": {"content": response.choices[0].message.content}}
        ]
    }


# Function to get image analysis using Google Gemini models
def get_image_analysis_google(api_key, model_name, prompt, base64_image):
    client = google_genai.Client(api_key=api_key)
    from google.genai import types as google_types

    blob = google_types.Blob(data=base64.b64decode(base64_image), mime_type="image/jpeg")
    content = [
        google_types.Content(role="user", parts=[
            google_types.Part(text=prompt),
            google_types.Part(inlineData=blob),
        ])
    ]

    config = google_types.GenerateContentConfig()
    response = client.models.generate_content(model=model_name, contents=content, config=config)

    return {"choices": [{"message": {"content": response.text}}]}


# Function to get image analysis using Anthropic Claude models
def get_image_analysis_anthropic(api_key, model_name, prompt, base64_image, media_type="image/jpeg"):
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_name,
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_image,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    text = "".join(block.text for block in response.content if getattr(block, "text", None))
    return {"choices": [{"message": {"content": text}}]}


# Function to get threat model from the GPT response.
def get_threat_model(api_key, model_name, prompt):
    client = OpenAI(api_key=api_key)

    # For reasoning models (o1, o3, o3-mini, o4-mini), use a structured system prompt
    if model_name in ["o1", "o3", "o3-mini", "o4-mini"]:
        system_prompt = create_reasoning_system_prompt(
            task_description="Analyze the provided application description and generate a comprehensive threat model using the STRIDE methodology.",
            approach_description="""1. Carefully read and understand the application description
2. For each component and data flow:
   - Identify potential Spoofing threats
   - Identify potential Tampering threats
   - Identify potential Repudiation threats
   - Identify potential Information Disclosure threats
   - Identify potential Denial of Service threats
   - Identify potential Elevation of Privilege threats
3. For each identified threat:
   - Describe the specific scenario
   - Analyze the potential impact
4. Generate improvement suggestions based on identified threats
5. Format the output as a JSON object with 'threat_model' and 'improvement_suggestions' arrays"""
        )
        # Create completion with max_completion_tokens for reasoning models
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=4000
        )
    else:
        system_prompt = "You are a helpful assistant designed to output JSON."
        # Create completion with max_tokens for other models
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )

    # Convert the JSON string in the 'content' field to a Python dictionary
    response_content = json.loads(response.choices[0].message.content)

    return response_content


# Function to get threat model from the Azure OpenAI response.
def get_threat_model_azure(azure_api_endpoint, azure_api_key, azure_api_version, azure_deployment_name, prompt):
    client = AzureOpenAI(
        azure_endpoint = azure_api_endpoint,
        api_key = azure_api_key,
        api_version = azure_api_version,
    )

    response = client.chat.completions.create(
        model = azure_deployment_name,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
            {"role": "user", "content": prompt}
        ]
    )

    # Convert the JSON string in the 'content' field to a Python dictionary
    response_content = json.loads(response.choices[0].message.content)

    return response_content


# Function to get threat model from the Google response.
def get_threat_model_google(google_api_key, google_model, prompt):
    # Create a client with the Google API key
    client = google_genai.Client(api_key=google_api_key)
    
    # Set up safety settings to allow security content
    safety_settings = [
        google_genai.types.SafetySetting(
            category=google_genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=google_genai.types.HarmBlockThreshold.BLOCK_NONE
        ),
        google_genai.types.SafetySetting(
            category=google_genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=google_genai.types.HarmBlockThreshold.BLOCK_NONE
        ),
        google_genai.types.SafetySetting(
            category=google_genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=google_genai.types.HarmBlockThreshold.BLOCK_NONE
        ),
        google_genai.types.SafetySetting(
            category=google_genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=google_genai.types.HarmBlockThreshold.BLOCK_NONE
        )
    ]
    
    # Check if we're using a Gemini 2.5 model (which supports thinking capabilities)
    is_gemini_2_5 = "gemini-2.5" in google_model.lower()
    
    try:
        from google.genai import types as google_types
        if is_gemini_2_5:
            config = google_types.GenerateContentConfig(
                response_mime_type='application/json',
                safety_settings=safety_settings,
                thinking_config=google_types.ThinkingConfig(thinking_budget=1024)
            )
        else:
            config = google_types.GenerateContentConfig(
                response_mime_type='application/json',
                safety_settings=safety_settings
            )
        
        # Generate content using the configured settings
        response = client.models.generate_content(
            model=google_model,
            contents=prompt,
            config=config
        )
        
        # Extract Gemini 2.5 'thinking' content if present
        thinking_content = []
        for candidate in getattr(response, 'candidates', []):
            content = getattr(candidate, 'content', None)
            if content and hasattr(content, 'parts'):
                for part in content.parts:
                    if hasattr(part, 'thought') and part.thought:
                        thinking_content.append(str(part.thought))
        if thinking_content:
            joined_thinking = "\n\n".join(thinking_content)
            st.session_state['last_thinking_content'] = joined_thinking
        
    except Exception as e:
        st.error(f"Error generating content with Google AI: {str(e)}")
        return None
    
    try:
        # Parse the response text as JSON
        response_content = json.loads(response.text)
    except json.JSONDecodeError:
        st.error("Failed to parse JSON response from Google AI")
        return None
        
    return response_content

# Function to get threat model from the Mistral response.
def get_threat_model_mistral(mistral_api_key, mistral_model, prompt):
    client = Mistral(api_key=mistral_api_key)

    response = client.chat.complete(
        model = mistral_model,
        response_format={"type": "json_object"},
        messages=[
            UserMessage(content=prompt)
        ]
    )

    # Convert the JSON string in the 'content' field to a Python dictionary
    response_content = json.loads(response.choices[0].message.content)

    return response_content

# Function to get threat model from Ollama hosted LLM.
def get_threat_model_ollama(ollama_endpoint, ollama_model, prompt):
    """
    Get threat model from Ollama hosted LLM.
    
    Args:
        ollama_endpoint (str): The URL of the Ollama endpoint (e.g., 'http://localhost:11434')
        ollama_model (str): The name of the model to use
        prompt (str): The prompt to send to the model
        
    Returns:
        dict: The parsed JSON response from the model
        
    Raises:
        requests.exceptions.RequestException: If there's an error communicating with the Ollama endpoint
        json.JSONDecodeError: If the response cannot be parsed as JSON
    """
    if not ollama_endpoint.endswith('/'):
        ollama_endpoint = ollama_endpoint + '/'
    
    url = ollama_endpoint + "api/generate"

    system_prompt = "You are a helpful assistant designed to output JSON."
    full_prompt = f"{system_prompt}\n\n{prompt}"

    data = {
        "model": ollama_model,
        "prompt": full_prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(url, json=data, timeout=60)  # Add timeout
        response.raise_for_status()  # Raise exception for bad status codes
        outer_json = response.json()
        
        try:
            # Parse the JSON response from the model's response field
            inner_json = json.loads(outer_json['response'])
            return inner_json
        except (json.JSONDecodeError, KeyError):

            raise
            
    except requests.exceptions.RequestException:

        raise

# Function to get threat model from the Claude response.
def get_threat_model_anthropic(anthropic_api_key, anthropic_model, prompt):
    client = Anthropic(api_key=anthropic_api_key)
    
    # Check if we're using Claude 3.7
    is_claude_3_7 = "claude-3-7" in anthropic_model.lower()
    
    # Check if we're using extended thinking mode
    is_thinking_mode = "thinking" in anthropic_model.lower()
    
    # If using thinking mode, use the actual model name without the "thinking" suffix
    actual_model = "claude-3-7-sonnet-latest" if is_thinking_mode else anthropic_model
    
    try:
        # For Claude 3.7, use a more explicit prompt structure
        if is_claude_3_7:
            # Add explicit JSON formatting instructions to the prompt
            json_prompt = prompt + "\n\nIMPORTANT: Your response MUST be a valid JSON object with the exact structure shown in the example above. Do not include any explanatory text, markdown formatting, or code blocks. Return only the raw JSON object."
            
            # Configure the request based on whether thinking mode is enabled
            if is_thinking_mode:
                response = client.messages.create(
                    model=actual_model,
                    max_tokens=24000,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": 16000
                    },
                    system="You are a JSON-generating assistant. You must ONLY output valid, parseable JSON with no additional text or formatting.",
                    messages=[
                        {"role": "user", "content": json_prompt}
                    ],
                    timeout=600  # 10-minute timeout
                )
            else:
                response = client.messages.create(
                    model=actual_model,
                    max_tokens=4096,
                    system="You are a JSON-generating assistant. You must ONLY output valid, parseable JSON with no additional text or formatting.",
                    messages=[
                        {"role": "user", "content": json_prompt}
                    ],
                    timeout=300  # 5-minute timeout
                )
        else:
            # Standard handling for other Claude models
            response = client.messages.create(
                model=actual_model,
                max_tokens=4096,
                system="You are a helpful assistant designed to output JSON. Your response must be a valid, parseable JSON object with no additional text, markdown formatting, or explanation. Do not include ```json code blocks or any other formatting - just return the raw JSON object.",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                timeout=300  # 5-minute timeout
            )
        
        # Combine all text blocks into a single string
        if is_thinking_mode:
            # For thinking mode, we need to extract only the text content blocks
            full_content = ''.join(block.text for block in response.content if block.type == "text")
            
            # Store thinking content in session state for debugging/transparency (optional)
            thinking_content = ''.join(block.thinking for block in response.content if block.type == "thinking")
            if thinking_content:
                st.session_state['last_thinking_content'] = thinking_content
        else:
            # Standard handling for regular responses
            full_content = ''.join(block.text for block in response.content)
        
        # Parse the JSON response
        try:
            # Check for and fix common JSON formatting issues
            if is_claude_3_7:
                # Sometimes Claude 3.7 adds trailing commas which are invalid in JSON
                full_content = full_content.replace(",\n  ]", "\n  ]").replace(",\n]", "\n]")
                
                # Sometimes it adds comments which are invalid in JSON
                full_content = re.sub(r'//.*?\n', '\n', full_content)
            
            response_content = json.loads(full_content)
            return response_content
        except json.JSONDecodeError as e:
            # Create a fallback response
            fallback_response = {
                "threat_model": [
                    {
                        "Threat Type": "Error",
                        "Scenario": "Failed to parse Claude response",
                        "Potential Impact": "Unable to generate threat model"
                    }
                ],
                "improvement_suggestions": [
                    "Try again - sometimes the model returns a properly formatted response on subsequent attempts",
                    "Check the logs for detailed error information"
                ]
            }
            return fallback_response
            
    except Exception as e:
        # Handle timeout and other errors
        error_message = str(e)
        st.error(f"Error with Anthropic API: {error_message}")
        
        # Create a fallback response for timeout or other errors
        fallback_response = {
            "threat_model": [
                {
                    "Threat Type": "Error",
                    "Scenario": f"API Error: {error_message}",
                    "Potential Impact": "Unable to generate threat model"
                }
            ],
            "improvement_suggestions": [
                "For complex applications, try simplifying the input or breaking it into smaller components",
                "If you're using extended thinking mode and encountering timeouts, try the standard model instead",
                "Consider reducing the complexity of the application description"
            ]
        }
        return fallback_response

# Function to get threat model from LM Studio Server response.
def get_threat_model_lm_studio(lm_studio_endpoint, model_name, prompt):
    client = OpenAI(
        base_url=f"{lm_studio_endpoint}/v1",
        api_key="not-needed"  # LM Studio Server doesn't require an API key
    )

    # Define the expected response structure
    threat_model_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "threat_model_response",
            "schema": {
                "type": "object",
                "properties": {
                    "threat_model": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Threat Type": {"type": "string"},
                                "Scenario": {"type": "string"},
                                "Potential Impact": {"type": "string"}
                            },
                            "required": ["Threat Type", "Scenario", "Potential Impact"]
                        }
                    },
                    "improvement_suggestions": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["threat_model", "improvement_suggestions"]
            }
        }
    }

    response = client.chat.completions.create(
        model=model_name,
        response_format=threat_model_schema,
        messages=[
            {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=4000,
    )

    # Convert the JSON string in the 'content' field to a Python dictionary
    response_content = json.loads(response.choices[0].message.content)

    return response_content

# Function to get threat model from the Groq response.
def get_threat_model_groq(groq_api_key, groq_model, prompt):
    client = Groq(api_key=groq_api_key)

    response = client.chat.completions.create(
        model=groq_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
            {"role": "user", "content": prompt}
        ]
    )

    # Process the response using our utility function
    reasoning, response_content = process_groq_response(
        response.choices[0].message.content,
        groq_model,
        expect_json=True
    )
    
    # If we got reasoning, display it in an expander in the UI
    if reasoning:
        with st.expander("View model's reasoning process", expanded=False):
            st.write(reasoning)

    return response_content