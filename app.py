import os
import uuid
import base64
import PyPDF2
import docx
import pandas as pd
import numpy as np
import chromadb
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
from langchain_text_splitters import RecursiveCharacterTextSplitter
from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from openai import OpenAI

load_dotenv()

# Initialize Flask
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configurations
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
STATIC_FOLDER = os.path.join(app.root_path, 'static')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'docx', 'xlsx', 'xls', 'txt', 'csv'}

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    client = OpenAI(api_key=api_key)
else:
    client = None
    print("WARNING: OPENAI_API_KEY environment variable is not set. OpenAI features will be unavailable.")

# Initialize ChromaDB
chromadb_client = chromadb.PersistentClient(path=os.path.join(app.root_path, 'chroma_db'))

# Create/get chroma collection
collection = chromadb_client.get_or_create_collection(name="documents")


def get_openai_embeddings(texts: list[str]) -> list[list[float]]:
    if not client:
        raise ValueError("OPENAI_API_KEY is not configured. Please set your OPENAI_API_KEY environment variable.")
    response = client.embeddings.create(
        input=texts,
        model="text-embedding-3-small"
    )
    return [data.embedding for data in response.data]


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def extract_text_from_pdf(file_path):
    text = ""
    with open(file_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text


def extract_text_from_docx(file_path):
    doc = docx.Document(file_path)
    text = []
    for paragraph in doc.paragraphs:
        text.append(paragraph.text)
    return '\n'.join(text)


def extract_text_from_excel(file_path):
    text = ""
    try:
        xls = pd.ExcelFile(file_path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            text += f"Sheet: {sheet_name}\n"
            text += df.to_string(index=False) + "\n\n"
    except Exception as e:
        print(f"Error reading Excel: {e}")
    return text


def extract_text_from_csv(file_path):
    try:
        df = pd.read_csv(file_path)
        return df.to_string(index=False)
    except Exception as e:
        print(f"Error reading csv: {e}")
        return ""


def extract_text_from_text(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading txt: {e}")
        return ""


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Extract text based on file type
        ext = filename.rsplit('.', 1)[1].lower()
        if ext == 'pdf':
            text = extract_text_from_pdf(file_path)
        elif ext == 'docx':
            text = extract_text_from_docx(file_path)
        elif ext in ['xlsx', 'xls']:
            text = extract_text_from_excel(file_path)
        elif ext == "csv":
            text = extract_text_from_csv(file_path)
        elif ext == "txt":
            text = extract_text_from_text(file_path)
        else:
            return jsonify({'error': 'Unsupported file format'}), 400

        # Split text into chunks
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = text_splitter.split_text(text)

        if not chunks:
            return jsonify({'error': 'No text found in file'}), 400

        # Generate embeddings and store in ChromaDB
        embeddings = get_openai_embeddings(chunks)

        # Add metadata and unique IDs
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [{'source': filename} for _ in chunks]

        collection.add(
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

        return jsonify({'message': f"File '{filename}' processed successfully."})

    return jsonify({'error': 'Invalid file format'}), 400


@app.route('/query', methods=['POST'])
def query():
    if not client:
        return jsonify({'error': 'OpenAI API Key is not configured. Please set the OPENAI_API_KEY environment variable.'}), 500

    data = request.get_json() or {}
    query_text = data.get('query', '').strip()
    if not query_text:
        return jsonify({'error': 'Empty query'}), 400

    # Retrieve matching chunks from database
    context = ""
    try:
        count = collection.count()
        if count > 0:
            query_embedding = get_openai_embeddings([query_text])[0]
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(3, count)
            )
            if results and results.get('documents') and len(results['documents'][0]) > 0:
                context = "\n".join(results['documents'][0])
    except Exception as e:
        print(f"Error querying ChromaDB: {e}")

    # Build Prompt
    system_prompt = "You are a helpful multi-modal AI Assistant."
    if context:
        user_prompt = f"Use the following document chunks as context to answer the user question. If the answer is not in the context, use your own knowledge.\n\nContext:\n{context}\n\nQuestion: {query_text}\nAnswer:"
    else:
        user_prompt = query_text

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        answer = completion.choices[0].message.content
        return jsonify({'answer': answer})
    except Exception as e:
        print("OpenAI Error:", e)
        return jsonify({'error': str(e)}), 500


@app.route('/generate_image', methods=['POST'])
def generate_image():
    if not client:
        return jsonify({'error': 'OpenAI API Key is not configured. Please set the OPENAI_API_KEY environment variable.'}), 500

    data = request.get_json() or {}
    prompt = data.get('prompt') or data.get('promt', '').strip()
    if not prompt:
        return jsonify({'error': 'Empty prompt'}), 400

    try:
        image_base64 = None

        # 1. Attempt using custom response / proxy API if configured
        if hasattr(client, 'responses'):
            try:
                response = client.responses.create(
                    model="gpt-5",
                    input=prompt,
                    tools=[{'type': "image_generation"}]
                )
                image_data = [
                    output.result
                    for output in getattr(response, 'output', [])
                    if getattr(output, 'type', '') == "image_generation_call"
                ]
                if image_data:
                    image_base64 = image_data[0]
            except Exception as proxy_err:
                print("Custom responses API failed, falling back to standard image generation:", proxy_err)

        # 2. Fallback to standard OpenAI DALL-E image generation
        if not image_base64:
            dalle_response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                response_format="b64_json"
            )
            image_base64 = dalle_response.data[0].b64_json

        if image_base64:
            # Handle potential data URL prefix
            if isinstance(image_base64, str) and ',' in image_base64:
                image_base64 = image_base64.split(',', 1)[1]

            filename = f"gen_{uuid.uuid4().hex}.png"
            image_path = os.path.join(STATIC_FOLDER, filename)

            with open(image_path, "wb") as f:
                f.write(base64.b64decode(image_base64))

            image_url = url_for('static', filename=filename)
            return jsonify({'image_url': image_url})
        else:
            return jsonify({'error': 'No image data returned from API'}), 500

    except Exception as e:
        print("Image generation error:", e)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)