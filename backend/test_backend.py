import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables relative to this file
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add backend directory to path so we can import local modules
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from pdf_processor import process_pdf
from pdf_generator import generate_summary_pdf
from ai_summarizer import summarize_pdf

# Mock summary data for generator testing
MOCK_SUMMARY = {
    "title": "Collaborative Lifelong Learning among Distributed Agents (CoLLA)",
    "overall_summary": "This paper introduces CoLLA, a novel framework for collaborative lifelong learning among distributed agents. Each agent learns a dictionary of task-specific representations, and agents collaborate to share learned knowledge dictionaries, thereby reducing communication costs and enhancing learning speeds on edge systems. The paper demonstrates CoLLA outperforming non-collaborative baselines.",
    "main_idea": "CoLLA introduces collaborative lifelong learning among distributed agents by sharing learned knowledge dictionaries, enabling rapid adaptation to new tasks on edge systems.",
    "problem_solved": "Traditional lifelong learning methods operate in isolation and do not leverage collaborative knowledge transfer, resulting in high computing loads and communication bottlenecks for edge nodes.",
    "assumptions": [
        "Homogeneous agent environment setups.",
        "Synchronous agent tasks updates.",
        "Reliable communication links between edge nodes.",
        "Fixed communication network topology."
    ],
    "limitations": [
        "Tested only on small-scale datasets (MNIST and CIFAR-10).",
        "Requires synchronous agent updates.",
        "Higher setup costs for initial shared dictionaries."
    ],
    "results_conclusion": "CoLLA achieved a 15% relative improvement in task accuracy and a 3x reduction in training iterations compared to state-of-the-art decentralized lifelong learning methods. The authors conclude that decentralized dictionary sharing is a scalable solution.",
    "real_world_impact": "This research is highly applicable to autonomous vehicles, where edge intelligence must adapt to new driving environments locally while sharing knowledge securely, and federated IoT systems.",
    "graphs_figures": [
        {
            "title": "Figure 3: Learning Accuracy Comparison",
            "explanation": "This chart compares learning accuracy of CoLLA with baseline methods over time. CoLLA reaches peak accuracy of 92% in 20 epochs, while baseline methods reach only 78% after 50 epochs, proving the benefit of task-dictionary sharing."
        },
        {
            "title": "Figure 5: Communication Cost Analysis",
            "explanation": "A line graph plotting communication overhead (MB) against the number of agents. CoLLA maintains a flat cost curve, showing sub-linear growth compared to baseline models which grow exponentially, illustrating efficient bandwidth usage."
        }
      ]
}

def create_dummy_pdf(filename: str):
    """
    Generates a simple, valid 2-page PDF file programmatically using ReportLab
    so that we have a real PDF file for local testing.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    
    story = [
        Paragraph("<b>Mock Research Paper Title</b>", styles["Heading1"]),
        Spacer(1, 20),
        Paragraph("Abstract: This is a programmatically generated mock PDF file used to verify that our PDF processor and PyMuPDF parse system metadata and text extraction are functioning correctly.", styles["BodyText"]),
        Spacer(1, 10),
        Paragraph("Introduction: Large language models require structured summaries of long research documents. In this paper, we demonstrate how Gemini 2.5 Flash acts as a reliable multimodal summarizing assistant.", styles["BodyText"]),
        Spacer(1, 100),
        Paragraph("<i>Page 1 of the mock document. Proceed to page 2 for conclusions.</i>", styles["Normal"])
    ]
    
    # Simple build
    doc.build(story)
    print(f"Created mock PDF file: {filename}")

def run_tests():
    print("=== STARTING BACKEND INTEGRATION TESTS ===")
    
    mock_in_pdf = os.path.join(BASE_DIR, "test_dummy_input.pdf")
    mock_out_pdf = os.path.join(BASE_DIR, "test_summary_report.pdf")
    
    # Test 1: Create a valid test PDF
    try:
        create_dummy_pdf(mock_in_pdf)
    except Exception as e:
        print(f"ERROR: Failed to create dummy PDF: {e}")
        return
        
    # Test 2: Verify pdf_processor.py
    print("\n--- Test 2: Validating PDF local parsing ---")
    info = process_pdf(mock_in_pdf)
    print("Parsed Metadata Results:")
    print(f"  - Title: {info['title']}")
    print(f"  - Author: {info['author']}")
    print(f"  - Pages: {info['page_count']}")
    print(f"  - Valid: {info['is_valid']}")
    
    if not info["is_valid"] or info["page_count"] == 0:
        print("ERROR: PDF Processor failed to validate or read the dummy PDF.")
        cleanup_temp_files(mock_in_pdf, mock_out_pdf)
        return
    print("SUCCESS: PDF local parsing functions correctly!")

    # Test 3: Verify pdf_generator.py (ReportLab rendering)
    print("\n--- Test 3: Validating PDF Report Generation ---")
    try:
        generate_summary_pdf(MOCK_SUMMARY, "test_dummy_input.pdf", mock_out_pdf)
        if os.path.exists(mock_out_pdf) and os.path.getsize(mock_out_pdf) > 0:
            print(f"SUCCESS: ReportLab successfully compiled report. PDF size: {os.path.getsize(mock_out_pdf)} bytes.")
            print(f"File created at: {mock_out_pdf}")
        else:
            print("ERROR: Generated report PDF is missing or empty.")
            cleanup_temp_files(mock_in_pdf, mock_out_pdf)
            return
    except Exception as e:
        print(f"ERROR: ReportLab failed to generate summary PDF: {e}")
        cleanup_temp_files(mock_in_pdf, mock_out_pdf)
        return

    # Test 4: Verify Gemini API connectivity (optional)
    print("\n--- Test 4: Validating Gemini API Integration (Optional) ---")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("SKIP: GEMINI_API_KEY environment variable is not configured. Skipping active Gemini API check.")
        print("Please configure GEMINI_API_KEY in backend/.env to run active AI tests.")
    else:
        print("API Key detected. Sending mock PDF to Gemini API...")
        try:
            ai_result = summarize_pdf(mock_in_pdf)
            if "error" in ai_result:
                print(f"ERROR: Gemini API returned an error: {ai_result['error']}")
            else:
                print("SUCCESS: Gemini API processed PDF and returned structured JSON summary:")
                print(f"  - Title: {ai_result.get('title')}")
                print(f"  - Overall Summary: {ai_result.get('overall_summary')[:100]}...")
                print(f"  - Main Idea: {ai_result.get('main_idea')}")
                print(f"  - Detected Figures Count: {len(ai_result.get('graphs_figures', []))}")
        except Exception as e:
            print(f"ERROR: Gemini API interaction failed: {e}")
            
    print("\n=== TESTS COMPLETED ===")
    
def cleanup_temp_files(in_path, out_path):
    if os.path.exists(in_path):
        os.remove(in_path)
    # Note: we keep the output summary PDF report so that the developer can visually check it!
    print("Temporary input file cleaned up.")

if __name__ == "__main__":
    run_tests()
