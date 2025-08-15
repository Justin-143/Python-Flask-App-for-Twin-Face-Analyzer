import base64
import json
import time
from flask import Flask, request, jsonify, render_template_string
from threading import Lock
import random

# Initialize the Flask application
app = Flask(__name__)

# A simple lock to prevent race conditions if multiple requests come in quickly
analysis_lock = Lock()

# --- HTML/CSS/JavaScript for the Front-end ---
# This is a single string that will be served as the main web page.
# It uses Tailwind CSS for styling, embedded as a script tag.
# It uses JavaScript to access the webcam, capture an image, and send it to the Flask backend.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elegant Twin Face Analyzer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen p-4">

    <div class="w-full max-w-2xl bg-white rounded-xl shadow-lg p-6 space-y-6">
        <h1 class="text-4xl font-bold text-center text-gray-800">
            Elegant Twin Face Analyzer
        </h1>
        <p class="text-center text-gray-600">
            A real-time AI system to differentiate between identical twins.
        </p>

        <!-- Analysis Mode Selection -->
        <div class="flex items-center justify-center gap-4">
            <label for="analysis-mode" class="text-gray-700 font-semibold">Analysis Mode:</label>
            <select id="analysis-mode" class="rounded-lg shadow-md border border-gray-300 p-2">
                <option value="standard">Standard Face Recognition</option>
                <option value="twin" selected>Twin Specific Analysis</option>
            </select>
        </div>

        <!-- Video feed container -->
        <div class="relative w-full aspect-video bg-gray-900 rounded-xl overflow-hidden shadow-inner">
            <video id="webcam-video" autoplay playsinline class="w-full h-full object-cover"></video>
            <canvas id="overlay-canvas" class="absolute top-0 left-0 w-full h-full"></canvas>
            <div id="no-camera-message" class="absolute inset-0 hidden items-center justify-center text-gray-500 text-lg">
                Camera feed is not available.
            </div>
        </div>

        <!-- Control buttons -->
        <div class="flex justify-center gap-4">
            <button id="start-btn" onclick="startCamera()" class="px-6 py-3 bg-green-600 text-white font-semibold rounded-lg shadow-md hover:bg-green-700 transition duration-300">
                Start Camera
            </button>
            <button id="analyze-btn" onclick="runAnalysis()" class="px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg shadow-md hover:bg-blue-700 transition duration-300 hidden">
                Run Analysis
            </button>
            <button id="stop-btn" onclick="stopCamera()" class="px-6 py-3 bg-red-600 text-white font-semibold rounded-lg shadow-md hover:bg-red-700 transition duration-300 hidden">
                Stop Camera
            </button>
        </div>

        <!-- Result display -->
        <div id="result-container" class="p-4 rounded-lg bg-gray-50 shadow-md hidden">
            <h3 class="text-xl font-bold mb-2 text-gray-700">Analysis Results:</h3>
            <pre id="result-display" class="whitespace-pre-wrap text-sm text-gray-600 bg-gray-100 p-3 rounded-md"></pre>
        </div>

        <!-- Custom Modal for Alerts -->
        <div id="custom-modal" class="fixed inset-0 bg-gray-900 bg-opacity-50 flex items-center justify-center hidden">
            <div class="bg-white p-6 rounded-lg shadow-xl max-w-sm w-full">
                <h3 class="text-xl font-bold mb-4">Warning</h3>
                <p id="modal-message" class="text-gray-700 mb-6"></p>
                <div class="flex justify-end">
                    <button onclick="closeModal()" class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
                        OK
                    </button>
                </div>
            </div>
        </div>

    </div>

    <script>
        // JavaScript for webcam access and communication with the Flask server
        const video = document.getElementById('webcam-video');
        const overlayCanvas = document.getElementById('overlay-canvas');
        const ctx = overlayCanvas.getContext('2d');
        const noCameraMessage = document.getElementById('no-camera-message');
        const startBtn = document.getElementById('start-btn');
        const analyzeBtn = document.getElementById('analyze-btn');
        const stopBtn = document.getElementById('stop-btn');
        const resultContainer = document.getElementById('result-container');
        const resultDisplay = document.getElementById('result-display');
        const analysisMode = document.getElementById('analysis-mode');
        const modal = document.getElementById('custom-modal');
        const modalMessage = document.getElementById('modal-message');
        let stream;

        // Function to show a custom modal instead of alert()
        function showModal(message) {
            modalMessage.textContent = message;
            modal.classList.remove('hidden');
        }

        // Function to close the custom modal
        function closeModal() {
            modal.classList.add('hidden');
        }

        // Function to start the webcam feed
        async function startCamera() {
            try {
                // Request access to the user's camera
                stream = await navigator.mediaDevices.getUserMedia({ video: true });
                video.srcObject = stream;
                video.style.display = 'block';
                noCameraMessage.style.display = 'none';

                // Update button visibility
                startBtn.classList.add('hidden');
                analyzeBtn.classList.remove('hidden');
                stopBtn.classList.remove('hidden');

            } catch (err) {
                console.error("Error accessing the webcam: ", err);
                video.style.display = 'none';
                noCameraMessage.style.display = 'flex';
                showModal("Could not access the webcam. Please check your permissions.");
                // Update button visibility
                startBtn.classList.remove('hidden');
                analyzeBtn.classList.add('hidden');
                stopBtn.classList.add('hidden');
            }
        }

        // Function to stop the webcam feed
        function stopCamera() {
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
                stream = null;
            }
            video.srcObject = null;
            ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

            // Update button visibility
            startBtn.classList.remove('hidden');
            analyzeBtn.classList.add('hidden');
            stopBtn.classList.add('hidden');
            resultContainer.classList.add('hidden');
        }

        // Function to draw bounding boxes and labels on the canvas
        function drawFaceBoxes(faces, videoWidth, videoHeight) {
            // Resize canvas to match video dimensions
            overlayCanvas.width = videoWidth;
            overlayCanvas.height = videoHeight;
            ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

            ctx.lineWidth = 2;
            ctx.strokeStyle = '#00ff00';
            ctx.fillStyle = '#00ff00';
            ctx.font = '16px Inter';

            faces.forEach(face => {
                const { box, score, id } = face;
                // Draw the bounding box
                ctx.strokeRect(box[0], box[1], box[2], box[3]);
                // Draw the label with score and ID
                const label = `ID: ${id}, Score: ${score.toFixed(2)}`;
                ctx.fillText(label, box[0], box[1] > 20 ? box[1] - 5 : box[1] + 20);
            });
        }

        // Function to capture a frame and send it to the backend for analysis
        async function runAnalysis() {
            if (!stream) {
                showModal("Please start the camera first.");
                return;
            }

            analyzeBtn.disabled = true;
            analyzeBtn.textContent = 'Analyzing...';
            resultContainer.classList.remove('hidden');
            resultDisplay.textContent = 'Processing...';

            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctxTemp = canvas.getContext('2d');
            ctxTemp.drawImage(video, 0, 0, canvas.width, canvas.height);

            const imageData = canvas.toDataURL('image/jpeg').split(',')[1];
            const mode = analysisMode.value;

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image: imageData, mode: mode })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                resultDisplay.textContent = JSON.stringify(data, null, 2);
                
                // Draw the bounding boxes from the backend response
                if (data.faces) {
                    drawFaceBoxes(data.faces, video.videoWidth, video.videoHeight);
                } else {
                    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
                }

            } catch (error) {
                console.error('Error during analysis:', error);
                resultDisplay.textContent = `Error: ${error.message}`;
                showModal("An error occurred during analysis. Check the console for details.");
            } finally {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = 'Run Analysis';
            }
        }
    </script>
</body>
</html>
"""

# --- Backend Routes ---

@app.route('/')
def index():
    """
    Main route to serve the HTML front-end.
    """
    return render_template_string(HTML_TEMPLATE)

@app.route('/analyze', methods=['POST'])
def analyze():
    """
    API endpoint to receive image data and run the analysis.
    This route now handles different analysis modes.
    """
    with analysis_lock:
        try:
            # Get the image data and analysis mode from the request body
            data = request.get_json()
            image_data_base64 = data.get('image')
            mode = data.get('mode', 'standard')

            if not image_data_base64:
                return jsonify({"error": "No image data received"}), 400

            # Decode the base64 image data (optional, depends on your model's needs)
            # image_data_bytes = base64.b64decode(image_data_base64)
            
            # --- Placeholder for the actual AI model integration ---
            # Here, you would load your trained model and pass it the image data.
            # The logic below simulates different results based on the 'mode' variable.
            # You would replace this entire section with your real computer vision pipeline.

            print(f"Received request for analysis mode: {mode}")
            time.sleep(2)  # Simulate a 2-second analysis

            if mode == 'twin':
                # Simulate a random outcome: twins (70% chance) or not twins (30% chance)
                if random.random() < 0.7:
                    # Case 1: They are twins
                    faces = [
                        {"id": "Twin A", "score": random.uniform(0.95, 0.99), "box": [100, 50, 150, 200]},
                        {"id": "Twin B", "score": random.uniform(0.95, 0.99), "box": [400, 50, 150, 200]}
                    ]
                    result = {
                        "message": "Analysis complete: Two highly similar faces detected. They are a match.",
                        "faces": faces,
                        "is_twin_match": True
                    }
                else:
                    # Case 2: They are not twins, despite two faces being detected
                    faces = [
                        {"id": "Person 1", "score": random.uniform(0.8, 0.9), "box": [100, 50, 150, 200]},
                        {"id": "Person 2", "score": random.uniform(0.8, 0.9), "box": [400, 50, 150, 200]}
                    ]
                    result = {
                        "message": "Analysis complete: Two different faces detected. They are not a match.",
                        "faces": faces,
                        "is_twin_match": False
                    }
            else: # Standard mode
                faces = [
                    {"id": f"Person {random.randint(1, 100)}", "score": random.uniform(0.7, 0.9), "box": [250, 100, 150, 200]}
                ]
                result = {
                    "message": f"Analysis complete for mode: {mode}",
                    "faces": faces,
                    "is_twin_match": False
                }
            # --- End of placeholder logic ---

            # Return the result as a JSON response
            return jsonify(result)

        except Exception as e:
            app.logger.error(f"An error occurred during image analysis: {e}")
            return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # You can install Flask with: pip install Flask
    # Run the server in debug mode.
    # The app will be available at http://127.0.0.1:5000
    app.run(debug=True)
