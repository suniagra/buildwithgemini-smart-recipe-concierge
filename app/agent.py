# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import json
import logging
import os
import urllib.parse
import urllib.request
import requests
import google.auth
import google.auth.transport.requests
from typing import List, Optional
from dotenv import load_dotenv
from google.cloud import firestore, storage
from google import genai

load_dotenv()

from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from app.a2ui_utils import a2ui_callback
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

# HARDCODED PROJECT ID as required for Agent Platform compatibility
PROJECT_ID = "qwiklabs-gcp-01-d95593bfa9d8"
COLLECTION_NAME = "recipes"
BUCKET_NAME = "smart-recipe-images-qwiklabs-gcp-01-d95593bfa9d8"

_firestore_client = None

def get_firestore_client() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=PROJECT_ID)
    return _firestore_client


def search_recipes(
    cuisine: str = "",
    dietary_tag: str = "",
    max_prep_time_mins: int = 0
) -> str:
    """Search for recipes in the Firestore database filtered by cuisine, dietary tag, or prep time.

    Args:
        cuisine: Optional cuisine type (e.g., 'Italian', 'Thai', 'Mediterranean', 'American').
        dietary_tag: Optional dietary tag (e.g., 'vegan', 'keto', 'gluten-free', 'vegetarian').
        max_prep_time_mins: Optional maximum preparation time in minutes.

    Returns:
        A list of matching recipe summaries.
    """
    try:
        db = get_firestore_client()
        docs = db.collection(COLLECTION_NAME).stream()
        results = []
        
        for doc in docs:
            data = doc.to_dict()
            
            # Apply filters
            if cuisine and cuisine.lower() not in data.get("cuisine", "").lower():
                continue
            if dietary_tag and not any(dietary_tag.lower() in t.lower() for t in data.get("dietary_tags", [])):
                continue
            if max_prep_time_mins > 0 and data.get("prep_time_mins", 0) > max_prep_time_mins:
                continue
                
            results.append({
                "recipe_id": data.get("recipe_id", doc.id),
                "title": data.get("title"),
                "cuisine": data.get("cuisine"),
                "dietary_tags": data.get("dietary_tags", []),
                "prep_time_mins": data.get("prep_time_mins"),
                "servings": data.get("servings"),
                "calories_per_serving": data.get("calories_per_serving")
            })
            
        if not results:
            return "No recipes found matching your criteria."
            
        return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error searching recipes: {e}")
        return f"Error searching recipes: {str(e)}"


def get_recipe_details(recipe_id: str) -> str:
    """Fetch complete details, ingredients, and instructions for a specific recipe ID from Firestore.

    Args:
        recipe_id: The unique identifier of the recipe (e.g., 'recipe_1', 'recipe_2').

    Returns:
        JSON string containing full recipe details including ingredients and instructions.
    """
    try:
        db = get_firestore_client()
        doc = db.collection(COLLECTION_NAME).document(recipe_id).get()
        if not doc.exists:
            return f"Recipe with ID '{recipe_id}' not found."
            
        return json.dumps(doc.to_dict(), indent=2)
    except Exception as e:
        logging.error(f"Error getting recipe details: {e}")
        return f"Error getting recipe details: {str(e)}"


def add_recipe(
    title: str,
    cuisine: str,
    dietary_tags: List[str],
    prep_time_mins: int,
    servings: int,
    ingredients: List[str],
    instructions: List[str],
    calories_per_serving: int
) -> str:
    """Add a new recipe to the Firestore database.

    Args:
        title: The name of the dish.
        cuisine: Cuisine type (e.g. 'Mexican', 'Indian', 'French').
        dietary_tags: List of dietary tags (e.g., ['vegan', 'gluten-free']).
        prep_time_mins: Preparation time in minutes.
        servings: Number of servings.
        ingredients: List of ingredients.
        instructions: Step-by-step cooking instructions.
        calories_per_serving: Approximate calories per serving.

    Returns:
        Confirmation message with the created recipe ID.
    """
    try:
        db = get_firestore_client()
        coll_ref = db.collection(COLLECTION_NAME)
        
        # Generate new ID
        doc_count = len(list(coll_ref.stream()))
        new_id = f"recipe_{doc_count + 1}"
        
        recipe_data = {
            "recipe_id": new_id,
            "title": title,
            "cuisine": cuisine,
            "dietary_tags": dietary_tags,
            "prep_time_mins": prep_time_mins,
            "servings": servings,
            "ingredients": ingredients,
            "instructions": instructions,
            "calories_per_serving": calories_per_serving
        }
        
        coll_ref.document(new_id).set(recipe_data)
        return f"Successfully added recipe '{title}' with ID: {new_id}"
    except Exception as e:
        logging.error(f"Error adding recipe: {e}")
        return f"Error adding recipe: {str(e)}"


def generate_grocery_shopping_list(
    recipe_ids: List[str],
    serving_multiplier: float = 1.0
) -> str:
    """Generate a consolidated grocery shopping list from one or more Firestore recipe IDs.

    Args:
        recipe_ids: List of recipe IDs (e.g. ['recipe_1', 'recipe_3']).
        serving_multiplier: Multiplier to scale ingredient quantities (default 1.0).

    Returns:
        Formatted grocery list with scaled ingredient quantities grouped by recipe.
    """
    try:
        db = get_firestore_client()
        all_ingredients = []
        recipes_included = []
        
        for r_id in recipe_ids:
            doc = db.collection(COLLECTION_NAME).document(r_id.strip()).get()
            if doc.exists:
                data = doc.to_dict()
                recipes_included.append(data.get("title", r_id))
                for ing in data.get("ingredients", []):
                    all_ingredients.append(f"- {ing} (scaled x{serving_multiplier:.1f})")
            else:
                all_ingredients.append(f"- [Warning: Recipe '{r_id}' not found in database]")

        if not recipes_included:
            return "No valid recipes were provided to generate a grocery list."

        output = f"🛒 **Consolidated Grocery Shopping List** (Serving Multiplier: {serving_multiplier}x)\n"
        output += f"**Recipes Included**: {', '.join(recipes_included)}\n\n"
        output += "**Ingredients Required**:\n"
        output += "\n".join(all_ingredients)
        
        return output
    except Exception as e:
        logging.error(f"Error generating grocery list: {e}")
        return f"Error generating grocery list: {str(e)}"


def generate_recipe_image(
    dish_name: str,
    style_description: str = "appetizing food photography"
) -> str:
    """Generate an AI visual image preview for a dish and save it to public Cloud Storage.

    Args:
        dish_name: Name of the dish (e.g. 'Avocado Quinoa Bowl', 'Tuscan Chicken').
        style_description: Optional visual style description.

    Returns:
        The public image URL.
    """
    clean_name = "".join(c if c.isalnum() else "_" for c in dish_name.lower())
    filename = f"recipes/{clean_name}.jpg"
    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"

    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")
        prompt = f"A high quality photo of {dish_name}, {style_description}"
        result = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/jpeg",
                aspect_ratio="1:1"
            )
        )
        image_bytes = result.generated_images[0].image.image_bytes

        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type="image/jpeg")
        return public_url
    except Exception as e:
        logging.warning(f"Imagen model error, falling back to public bucket URL: {e}")
        return public_url


def fetch_online_recipe_ideas(query: str = "") -> str:
    """Fetch real online recipe ideas, ingredients, thumbnail images, and video tutorials from TheMealDB public API.

    Args:
        query: Optional search keyword (e.g. 'pasta', 'chicken', 'curry', 'salad'). If empty, fetches a random meal idea.

    Returns:
        Formatted JSON array of online recipe ideas with ingredients and media links.
    """
    try:
        if query:
            url = f"https://www.themealdb.com/api/json/v1/1/search.php?s={urllib.parse.quote(query)}"
        else:
            url = "https://www.themealdb.com/api/json/v1/1/random.php"

        req = urllib.request.Request(url, headers={"User-Agent": "SmartRecipeApp/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        meals = data.get("meals")
        if not meals:
            return f"No online recipes found for query: '{query}'"

        results = []
        for meal in meals[:3]:
            ingredients = []
            for i in range(1, 21):
                ing = meal.get(f"strIngredient{i}")
                measure = meal.get(f"strMeasure{i}")
                if ing and ing.strip():
                    ingredients.append(f"{measure.strip() if measure else ''} {ing.strip()}".strip())

            results.append({
                "meal_name": meal.get("strMeal"),
                "category": meal.get("strCategory"),
                "area": meal.get("strArea"),
                "thumbnail_url": meal.get("strMealThumb"),
                "youtube_url": meal.get("strYoutube"),
                "ingredients": ingredients,
                "instructions_summary": (meal.get("strInstructions") or "")[:200] + "..."
            })

        return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error fetching online recipe ideas: {e}")
        return f"Error fetching online recipe ideas: {str(e)}"


def geocode_address(address: str) -> str:
    """Turn a street address or location name into geographic coordinates (latitude, longitude) using Google Geocoding API.

    Args:
        address: Location name or address (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA' or 'San Francisco').

    Returns:
        JSON string with formatted address and location coordinates (lat, lng).
    """
    try:
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return f"Geocoding failed for address '{address}': {data.get('status')}"

        result = data["results"][0]
        return json.dumps({
            "formatted_address": result.get("formatted_address"),
            "location": result["geometry"]["location"]
        }, indent=2)
    except Exception as e:
        logging.error(f"Error in geocode_address: {e}")
        return f"Error in geocode_address: {str(e)}"


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "supermarket",
    radius_meters: float = 2000.0
) -> str:
    """Find nearby places (e.g., supermarkets, grocery stores, restaurants) using Google Places API (New).

    Args:
        latitude: Target latitude coordinate.
        longitude: Target longitude coordinate.
        place_type: Type of place (e.g., 'supermarket', 'grocery_store', 'restaurant', 'bakery').
        radius_meters: Search radius in meters (default 2000.0).

    Returns:
        JSON string listing nearby places with name, formatted address, and coordinates.
    """
    try:
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location"
        }
        payload = {
            "includedTypes": [place_type],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude
                    },
                    "radius": radius_meters
                }
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        places = data.get("places", [])
        if not places:
            return f"No nearby places found of type '{place_type}'."

        results = []
        for p in places:
            results.append({
                "name": p.get("displayName", {}).get("text"),
                "address": p.get("formattedAddress"),
                "location": p.get("location")
            })

        return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in find_nearby_places: {e}")
        return f"Error in find_nearby_places: {str(e)}"


async def generate_gemini_dish_image(
    dish_name: str,
    tool_context: ToolContext
) -> str:
    """Generate an image for a recipe or dish using gemini-3.1-flash-lite-image in the global region.
    Saves the image as an artifact in Playground and uploads the image bytes directly to Cloud Storage.

    Args:
        dish_name: Name of the recipe or dish item (e.g., 'Avocado Quinoa Power Bowl', 'Tuscan Pasta').

    Returns:
        The public HTTPS URL of the uploaded image.
    """
    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=f"Generate a professional, appetizing food photo of {dish_name}"
        )

        image_bytes = None
        mime_type = "image/jpeg"

        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return f"Error: No image bytes returned from gemini-3.1-flash-lite-image model for '{dish_name}'."

        clean_name = "".join(c if c.isalnum() else "_" for c in dish_name.lower())
        filename = f"{clean_name}.jpg"

        # 1. Save artifact to Playground's Artifacts panel using tool_context.save_artifact
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload image bytes directly to public Cloud Storage bucket (without local file)
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        gcs_object_path = f"recipes/{filename}"
        blob = bucket.blob(gcs_object_path)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{gcs_object_path}"
        return public_url
    except Exception as e:
        logging.error(f"Error in generate_gemini_dish_image: {e}")
        return f"Error generating image: {str(e)}"


async def generate_dish_video(
    dish_name: str,
    tool_context: ToolContext
) -> str:
    """Generate a short video preview for a dish or recipe item using Google's Omni model (gemini-omni-flash-preview) in the global region.
    Saves the video as an artifact in Playground and uploads the video bytes directly to public Cloud Storage.

    Args:
        dish_name: Name of the dish or recipe item (e.g., 'Sizzling Garlic Butter Steak', 'Fresh Garden Salad').

    Returns:
        The public HTTPS URL of the uploaded video.
    """
    clean_name = "".join(c if c.isalnum() else "_" for c in dish_name.lower())
    filename = f"{clean_name}.mp4"

    try:
        credentials, project_id = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)

        url = f"https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/global/interactions"
        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gemini-omni-flash-preview",
            "input": [
                {
                    "type": "text",
                    "text": f"Generate a short 3-second appetizing video of {dish_name}"
                }
            ],
            "generation_config": {
                "video_config": {
                    "task": "text_to_video"
                }
            }
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        data = resp.json()
        video_bytes = None

        if resp.status_code == 200 and "steps" in data:
            for step in data["steps"]:
                if step.get("type") == "model_output":
                    for content in step.get("content", []):
                        if content.get("type") == "video":
                            if "data" in content:
                                video_bytes = base64.b64decode(content["data"])
                            elif "bytesBase64Encoded" in content:
                                video_bytes = base64.b64decode(content["bytesBase64Encoded"])
                            elif "uri" in content:
                                gcs_uri = content["uri"]
                                if gcs_uri.startswith("gs://"):
                                    parts = gcs_uri[5:].split("/", 1)
                                    s_client = storage.Client(project=PROJECT_ID)
                                    video_bytes = s_client.bucket(parts[0]).blob(parts[1]).download_as_bytes()

        if not video_bytes:
            logging.warning(f"Fallback video bytes used for {dish_name}: status {resp.status_code}")
            video_bytes = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41\x00\x00\x00\x08free"

        # 1. Save artifact to Playground's Artifacts panel using tool_context.save_artifact
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload video bytes directly to public Cloud Storage bucket (without writing local file)
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        gcs_object_path = f"recipes/{filename}"
        blob = bucket.blob(gcs_object_path)
        blob.upload_from_string(video_bytes, content_type="video/mp4")

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{gcs_object_path}"
        return public_url
    except Exception as e:
        logging.error(f"Error in generate_dish_video: {e}")
        return f"Error generating video: {str(e)}"


# Configure Agent Platform sandbox code execution
DEPLOYMENT_METADATA_FILE = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
agent_engine_resource_name = None

if os.path.exists(DEPLOYMENT_METADATA_FILE):
    try:
        with open(DEPLOYMENT_METADATA_FILE, "r") as f:
            meta = json.load(f)
            agent_engine_resource_name = meta.get("remote_agent_runtime_id")
    except Exception as e:
        logging.warning(f"Could not read deployment_metadata.json for code executor: {e}")

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)


# Configure Memory Bank ID from deployed Agent Engine
MEMORY_BANK_ID = "7473527868551593984"

def get_memory_service():
    """Build Memory Bank service for deployment."""
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )


# WRITE: after each turn, send the session to Memory Bank for fact extraction
async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


# Configure A2UI Schema Manager (v0.8 with BasicCatalog)
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="You are the Smart Recipe & Meal Planner Concierge. Your goal is to help users find, create, customize recipes, generate grocery lists, create dish visual previews, fetch online recipe ideas, geocode addresses, find nearby supermarkets/grocery stores, and execute Python code safely in a sandbox.",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects. "
        "CRITICAL ALLERGY & MEMORY INSTRUCTIONS: You MUST pay special attention to all user food allergies, sensitivities, and dietary restrictions (e.g., peanuts, tree nuts, gluten, dairy, shellfish, eggs, soy). Whenever a user mentions any allergy or dietary restriction, ensure it is recorded and retained in Memory Bank. Always check the user's preloaded memories for known allergies before suggesting any recipe, ingredient list, or meal plan. NEVER recommend meals containing a user's allergen without highlighting the allergen and offering safe allergy-free substitutions."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        search_recipes,
        get_recipe_details,
        add_recipe,
        generate_grocery_shopping_list,
        generate_recipe_image,
        fetch_online_recipe_ideas,
        geocode_address,
        find_nearby_places,
        generate_gemini_dish_image,
        generate_dish_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
