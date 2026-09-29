# Copyright 2026 Google LLC
# Seed script for Firestore recipes collection

import logging
from google.cloud import firestore

logging.basicConfig(level=logging.INFO)

# HARDCODED PROJECT ID as required for Agent Platform compatibility
PROJECT_ID = "qwiklabs-gcp-01-d95593bfa9d8"
COLLECTION_NAME = "recipes"

SEED_RECIPES = [
    {
        "recipe_id": "recipe_1",
        "title": "Avocado & Quinoa Power Bowl",
        "cuisine": "Mediterranean",
        "dietary_tags": ["vegan", "gluten-free"],
        "prep_time_mins": 15,
        "servings": 2,
        "ingredients": [
            "1 cup cooked quinoa",
            "1 ripe avocado, sliced",
            "1/2 cup cherry tomatoes",
            "1/4 cup cucumber, diced",
            "2 tbsp lemon-tahini dressing"
        ],
        "instructions": [
            "Arrange cooked quinoa in two bowls.",
            "Top with avocado slices, cherry tomatoes, and cucumber.",
            "Drizzle lemon-tahini dressing over the top and serve immediately."
        ],
        "calories_per_serving": 420
    },
    {
        "recipe_id": "recipe_2",
        "title": "Creamy Garlic Tuscan Chicken",
        "cuisine": "Italian",
        "dietary_tags": ["keto", "high-protein"],
        "prep_time_mins": 25,
        "servings": 4,
        "ingredients": [
            "4 chicken breasts",
            "1 tbsp olive oil",
            "1/2 cup heavy cream",
            "1/2 cup chicken broth",
            "1 tsp garlic powder",
            "1 cup spinach",
            "1/2 cup sun-dried tomatoes"
        ],
        "instructions": [
            "Sear chicken breasts in olive oil until golden brown.",
            "Remove chicken, add garlic, cream, broth, and sun-dried tomatoes to pan.",
            "Simmer until sauce thickens, add spinach and return chicken to pan."
        ],
        "calories_per_serving": 510
    },
    {
        "recipe_id": "recipe_3",
        "title": "Thai Red Curry Tofu & Vegetables",
        "cuisine": "Thai",
        "dietary_tags": ["vegan", "dairy-free"],
        "prep_time_mins": 30,
        "servings": 3,
        "ingredients": [
            "200g firm tofu, cubed",
            "1 tbsp red curry paste",
            "1 can coconut milk",
            "1 red bell pepper, sliced",
            "1 cup snap peas",
            "1 tbsp soy sauce"
        ],
        "instructions": [
            "Sauté red curry paste in 2 tbsp coconut milk until fragrant.",
            "Pour in remaining coconut milk, add tofu, bell pepper, and snap peas.",
            "Simmer for 15 minutes, stir in soy sauce, and serve warm."
        ],
        "calories_per_serving": 380
    },
    {
        "recipe_id": "recipe_4",
        "title": "Berry Acai Protein Smoothie Bowl",
        "cuisine": "American",
        "dietary_tags": ["vegetarian", "gluten-free"],
        "prep_time_mins": 10,
        "servings": 1,
        "ingredients": [
            "1 frozen acai packet",
            "1 cup frozen mixed berries",
            "1 scoop vanilla protein powder",
            "1/2 cup almond milk",
            "Toppings: chia seeds, sliced banana, granola"
        ],
        "instructions": [
            "Blend acai, berries, protein powder, and almond milk until thick.",
            "Pour into a bowl and top with chia seeds, banana slices, and granola."
        ],
        "calories_per_serving": 340
    }
]

def seed_database():
    db = firestore.Client(project=PROJECT_ID)
    logging.info(f"Connected to Firestore project: {PROJECT_ID}")
    
    for item in SEED_RECIPES:
        doc_ref = db.collection(COLLECTION_NAME).document(item["recipe_id"])
        doc_ref.set(item)
        logging.info(f"Seeded recipe '{item['title']}' (ID: {item['recipe_id']})")
        
    logging.info("Database seeding successfully completed!")

if __name__ == "__main__":
    seed_database()
