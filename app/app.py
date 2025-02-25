import streamlit as st
import tempfile
from PIL import Image
from io import BytesIO
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.prompts import PromptTemplate
from langchain_huggingface import HuggingFaceEndpoint
from huggingface_hub import InferenceClient
import json

from dotenv import load_dotenv
import os 
load_dotenv()

# Set your Hugging Face API key here
HF_API_KEY = os.getenv("HUGGINGFACE_API_TOKEN")

# -------------------------------
# Functions for each pipeline step
# -------------------------------

def load_and_split_pdf(pdf_file_path):
    """Loads a PDF file and returns a list of document objects."""
    loader = PyMuPDFLoader(pdf_file_path)
    documents = loader.load()
    return documents

def get_unified_book(documents):
    """Concatenates the page content of all documents into one string."""
    unified_book = ""
    for doc in documents:
        unified_book += doc.page_content
    return unified_book

def summarize_text(text, text_llm):
    """Summarizes the provided text using a LangChain chain."""
    summarize_prompt_template = PromptTemplate(
        input_variables=["text"],
        template="Summarize the following story text in a concise manner:\n\n{text}\n\nSummary:"
    )
    summarize_chain = summarize_prompt_template | text_llm
    summary = summarize_chain.invoke({"text": text})
    return summary

def generate_depiction_prompts(summary, text_llm, num_scenes, style):
    """Generates a list of depiction prompts (as a JSON array) for image generation from a story summary."""
    depiction_prompt_template = PromptTemplate(
        input_variables=["summary", "num_scenes", "style"],
        template="""
You are an AI assistant that generates visual depiction prompts for a text-to-image model.
Given the following summary of a child's story and the illustration style "{style}", generate exactly {num_scenes} distinct, short, and clear prompts that each describe one key scene from the story.
Output the result as a JSON array of strings (do not include any additional text or explanation).

Summary: {summary}
JSON Array of Prompts:
"""
    )
    depiction_chain = depiction_prompt_template | text_llm
    output_text = depiction_chain.invoke({"summary": summary, "num_scenes": num_scenes, "style": style})
    try:
        prompt_list = json.loads(output_text)
    except Exception as e:
        prompt_list = [line.strip() for line in output_text.splitlines() if line.strip()]
    return prompt_list

def generate_image(prompt_text, client):
    """Generates an image based on the prompt using the Hugging Face Inference API."""
    image_data = client.text_to_image(
        prompt_text,
        model="stabilityai/stable-diffusion-3.5-large"
    )
    # If image_data is already a PIL Image, return it directly.
    if isinstance(image_data, Image.Image):
        return image_data
    else:
        return Image.open(BytesIO(image_data))

# -------------------------------
# Initialize endpoints and clients
# -------------------------------

# Instantiate the text LLM endpoint using LangChain's HuggingFaceEndpoint
text_llm = HuggingFaceEndpoint(
    repo_id="meta-llama/Llama-3.2-3B-Instruct",
    temperature=0.2,
    huggingfacehub_api_token=HF_API_KEY,
)

# Instantiate the InferenceClient for image generation
client = InferenceClient(
    provider="hf-inference",
    api_key=HF_API_KEY
)

# -------------------------------
# Streamlit UI
# -------------------------------

st.title("Child Story Book Visualizer")
st.write("Upload a child's story book PDF to generate a summary, multiple visual depiction prompts in a chosen style, and AI-generated images for each scene.")

# Option: Allow the user to select the illustration style
style_option = st.selectbox(
    "Select Illustration Style",
    options=["Photorealistic", "Cartoon", "Watercolor", "Vintage", "Anime"],
    index=0
)

# Option: Allow the user to choose how many key scenes to generate
num_scenes = st.number_input(
    "Number of Key Scenes to Generate", min_value=1, max_value=10, value=3, step=1
)

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    # Save the uploaded file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_file_path = tmp_file.name

    st.write("Processing PDF...")
    documents = load_and_split_pdf(tmp_file_path)
    unified_book = get_unified_book(documents)
    st.write("PDF loaded. Total characters extracted:", len(unified_book))
    
    st.write("Generating summary...")
    summary = summarize_text(unified_book, text_llm)
    st.subheader("Summary")
    st.write(summary)
    
    st.write("Generating depiction prompts...")
    prompts = generate_depiction_prompts(summary, text_llm, num_scenes, style_option)
    st.subheader("Depiction Prompts")
    for i, prompt in enumerate(prompts, start=1):
        st.write(f"Scene {i}: {prompt}")
        # Generate images for each scene (one API call per prompt)
    images = []
    for i, prompt in enumerate(prompts, start=1):
        st.write(f"Generating image for Scene {i}...")
        try:
            # Each call to generate_image is separate
            image = generate_image(prompt, client)
            images.append(image)
        except Exception as e:
            st.error(f"Error generating image for Scene {i} with prompt '{prompt}': {e}")

    if images:
        st.subheader("Generated Images")
        st.image(images, caption=[f"Scene {i}" for i in range(1, len(images)+1)])
