# Required imports
import os
import re
from ibm_watson_machine_learning.foundation_models.utils.enums import ModelTypes
from ibm_watson_machine_learning.metanames import GenTextParamsMetaNames as GenParams
from ibm_watsonx_ai.foundation_models.utils.enums import EmbeddingTypes
from langchain_ibm import WatsonxEmbeddings, WatsonxLLM
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import chainlit as cl

# Defining credentials
credentials = {
    "url": "https://us-south.ml.cloud.ibm.com",
    "apikey": "*********************"
}

project_id = "*************************"

# Load PDFs from the "data" folder
pdf_folder = "data"
documents = []

# Check if the PDF folder exists
if not os.path.exists(pdf_folder):
    raise FileNotFoundError(f"The folder '{pdf_folder}' does not exist.")

for filename in os.listdir(pdf_folder):
    if filename.endswith(".pdf"):
        pdf_path = os.path.join(pdf_folder, filename)
        loader = PyPDFLoader(pdf_path)
        data = loader.load()
        documents += data

if not documents:
    raise ValueError("No PDF files found in the folder.")

# Clean and split the data
doc_id = 0
for doc in documents:
    doc.page_content = " ".join(doc.page_content.split())  # remove extra spaces
    doc.metadata["id"] = doc_id  # Add metadata with document ID
    doc_id += 1

# Split documents into chunks
text_splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=0)
docs = text_splitter.split_documents(documents)

# Using IBM embedding models
embeddings = WatsonxEmbeddings(
    model_id=EmbeddingTypes.IBM_SLATE_30M_ENG.value,
    url=credentials["url"],
    apikey=credentials["apikey"],
    project_id=project_id,
)

# Creating the vector store
vectorstore = Chroma.from_documents(documents=docs, embedding=embeddings)

# Setup retriever
retriever = vectorstore.as_retriever()

# Load and define the LLM model
model_id = ModelTypes.GRANITE_13B_CHAT_V2

parameters = {
    GenParams.DECODING_METHOD: 'greedy',
    GenParams.TEMPERATURE: 2,
    GenParams.TOP_P: 0,
    GenParams.TOP_K: 100,
    GenParams.MIN_NEW_TOKENS: 10,
    GenParams.MAX_NEW_TOKENS: 512,
    GenParams.REPETITION_PENALTY: 1.2,
    GenParams.STOP_SEQUENCES: ['B)', '\n'],
    GenParams.RETURN_OPTIONS: {
        'input_tokens': True, 'generated_tokens': True, 'token_logprobs': True, 'token_ranks': True,
    }
}

llm = WatsonxLLM(
    model_id=model_id.value,
    url=credentials.get("url"),
    apikey=credentials.get("apikey"),
    project_id=project_id,
    params=parameters
)

# Setup prompt template
template = """You are acting as a helpful rescuer assistant and you follow ethical guidelines and promote positive behavior. You always respond to greetings (for example, hi, hello, g'day, morning, afternoon, evening, night, what's up, nice to meet you, sup, etc) with "Hello! I am RescueX. How can I help you today?". Please do not say anything else and do not start a conversation..
Answer the question based only on the following context:

{context}

Question: {question}
"""

prompt = ChatPromptTemplate.from_template(template)

def format_docs(docs):
    return "\n\n".join([d.page_content for d in docs])

# Define the chain
chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

def sanitize_input(input_text):
    # Remove special characters and unnecessary spaces
    return re.sub(r'[\n\t]', ' ', input_text).strip()

# Chainlit chat interface
# Chainlit chat interface
@cl.on_message
async def main(message):
    try:
        # Extract the text content from the message object
        user_message = sanitize_input(message.content)

        # Prepare the inputs for the chain
        response = chain.invoke(user_message)  # Invoke the chain with the extracted text

        # Send the response back to the user
        await cl.Message(content=response).send()  # Correct function to send a message

    except Exception as e:
        # Send error message back to the user
        await cl.Message(content=f"Error: {str(e)}").send()  # Error handling
