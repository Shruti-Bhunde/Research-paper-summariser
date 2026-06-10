import os
import time
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# Load env variables using absolute path relative to this file's folder
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# Define structured schemas for Pydantic/Gemini output
class FigureExplanation(BaseModel):
    title: str = Field(
        description="The title, label, or reference of the graph or figure (e.g., 'Figure 3: Learning Accuracy Comparison')."
    )
    explanation: str = Field(
        description="Detailed explanation of the figure's visual contents, data, trend, axes, and conclusions."
    )

class PaperSummarySchema(BaseModel):
    overall_summary: str = Field(
        description="A complete, concise summary of the research paper in 150-300 words covering the problem, approach, results, and core contribution."
    )
    main_idea: str = Field(
        description="The central concept or core innovation of this paper. What is its main thesis?"
    )
    problem_solved: str = Field(
        description="What weakness, limitation, or research gap in previous systems is this paper trying to solve?"
    )
    assumptions: List[str] = Field(
        description="Key assumptions made by the authors during their research or design (e.g., network reliability, agent synchrony)."
    )
    limitations: List[str] = Field(
        description="Explicitly mentioned or implied limitations of the proposed approach (e.g., tested on small datasets, high computation costs)."
    )
    results_conclusion: str = Field(
        description="Summary of experimental findings, performance metrics, gains, and final conclusions."
    )
    real_world_impact: str = Field(
        description="Practical real-world applications of this research (e.g., autonomous driving, edge AI, smart healthcare)."
    )
    graphs_figures: List[FigureExplanation] = Field(
        description="A list of analyses for all figures, charts, and graphs detected in the paper. Explain what they show."
    )

def summarize_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    Uploads a PDF file to the Gemini API, generates a structured JSON summary
    conforming to the PaperSummarySchema, and deletes the uploaded PDF from Gemini's server.
    
    Inputs:
        pdf_path (str): The local path to the PDF file.
        
    Outputs:
        dict: The structured summary matching the PaperSummarySchema or containing an error.
    """
    # Load or refresh env variables dynamically (allows adding the key without restarting the server)
    load_dotenv(dotenv_path=env_path, override=True)
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        return {
            "error": "Gemini API Key is missing. Please add GEMINI_API_KEY to your backend/.env file."
        }
        
    # Configure Gemini API
    genai.configure(api_key=api_key)
    
    uploaded_file = None
    try:
        print(f"Uploading {pdf_path} to Gemini File API...")
        # Upload the PDF to Google Gemini File API (required for multimodal analysis)
        uploaded_file = genai.upload_file(path=pdf_path, mime_type="application/pdf")
        
        # Wait for file to transition from processing to active
        print("Waiting for file to be processed by Gemini...")
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = genai.get_file(uploaded_file.name)
            
        if uploaded_file.state.name != "ACTIVE":
            raise Exception(f"File upload failed. State: {uploaded_file.state.name}")
            
        print("File is active. Generating summary...")
        
        # Initialize Gemini 2.5 Flash model
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        prompt = (
            "Analyze the attached research paper PDF in detail. "
            "Please read the full text, equations, and examine all graphs, tables, and figures. "
            "Generate a highly accurate, structured JSON summary matching the schema provided. "
            "Ensure you analyze the visual diagrams/graphs and explain their data/conclusion in the graphs_figures list. "
            "Do not omit any sections."
        )
        
        # Generate content with structured JSON schema
        response = model.generate_content(
            [uploaded_file, prompt],
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": PaperSummarySchema,
                "temperature": 0.2
            }
        )
        
        # Parse the JSON response
        # Using eval/json parsing is bypassed since Gemini API SDK returns a structured response object
        # which we can access directly or load as text.
        import json
        summary_json = json.loads(response.text)
        return summary_json
        
    except Exception as e:
        print(f"Error during AI summarization: {str(e)}")
        return {
            "error": f"AI summarization failed: {str(e)}"
        }
        
    finally:
        # Always clean up and delete the PDF from Gemini's servers immediately after use
        if uploaded_file:
            try:
                print(f"Deleting uploaded file {uploaded_file.name} from Gemini API servers...")
                uploaded_file.delete()
                print("Deleted successfully.")
            except Exception as e:
                print(f"Could not delete uploaded file from Gemini servers: {e}")
