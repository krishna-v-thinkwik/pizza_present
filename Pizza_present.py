import os
from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import re

app = Flask(__name__)

# Setup Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
service_account_info = json.loads(os.environ["GOOGLE_CREDS_JSON"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
client = gspread.authorize(creds)

# Load main pizza menu
sheet = client.open("menu").worksheet("pizza menu")
data = sheet.get_all_records()

# Load toppings sheet
topping_sheet = client.open("menu").worksheet("toppings")
topping_records = topping_sheet.get_all_records()

@app.route('/')
def home():
    return "✅ Pizza order API is live."

@app.route('/check_order', methods=['POST'])
def check_order():
    input_data = request.get_json()

    names_raw = input_data.get("PizzaName", "").lower().strip()
    sizes_raw = input_data.get("PizzaSize", "").lower().strip()
    crusts_raw = input_data.get("PizzaCrust", "").lower().strip()
    toppings_raw = input_data.get("PizzaToppings", "").lower().strip()

    def singularize(word):
        word = word.strip().lower()
        return word[:-1] if word.endswith('s') and not word.endswith('ss') else word

    # Parse and normalize pizza orders
    pizza_orders = re.findall(r'(\d+)\s+([a-zA-Z ]+?)(?=\s*(?:and|$))', names_raw)
    pizza_orders = [(qty, singularize(name)) for qty, name in pizza_orders]

    sizes = [singularize(s.strip()) for s in (sizes_raw.split(" and ") if " and " in sizes_raw else [sizes_raw])]
    crusts = [singularize(c.strip()) for c in (crusts_raw.split(" and ") if " and " in crusts_raw else [crusts_raw])]
    toppings_input = [singularize(t.strip()) for t in (toppings_raw.split(" and ") if " and " in toppings_raw else [toppings_raw])]

    # Build a normalized toppings map from toppings sheet
    topping_map = {}
    for row in topping_records:
        if "Toppings" in row and row["Toppings"]:
            normalized = singularize(row["Toppings"])
            topping_map[normalized] = row["Toppings"]

    all_toppings = set(topping_map.keys())
    valid_toppings = [t for t in toppings_input if t in all_toppings]
    invalid_toppings = [t for t in toppings_input if t not in all_toppings]

    response = []
    all_available = True

    for idx, (qty, name) in enumerate(pizza_orders):
        size = sizes[idx] if idx < len(sizes) else sizes[0] if sizes else ""
        crust = crusts[idx] if idx < len(crusts) else crusts[0] if crusts else ""

        matched_items = [
            row for row in data
            if 'Name' in row and singularize(row['Name'].strip().lower()) == name
        ]

        if not matched_items:
            available_pizzas = sorted(set(row['Name'] for row in data))
            response.append(
                f"Sorry! we do not have {name.title()} pizza in our menu. However, here are some pizzas you can choose from: {', '.join(available_pizzas)}."
            )
            all_available = False
            continue

        matched_by_size = [row for row in matched_items if singularize(row['Size']) == size]
        if not matched_by_size:
            available_sizes = sorted(set(row['Size'] for row in matched_items))
            response.append(
                f"We do not have {name.title()} pizza in {size.title()} size but we do have it in {', '.join(s.title() for s in available_sizes)}."
            )
            all_available = False
            continue

        matched_by_crust = [row for row in matched_by_size if singularize(row['Crust']) == crust]
        if not matched_by_crust:
            available_crusts = sorted(set(row['Crust'] for row in matched_by_size))
            response.append(
                f"{name.title()} in {size.title()} size is not available with '{crust.title()}' crust. Available crusts: {', '.join(c.title() for c in available_crusts)}."
            )
            all_available = False
            continue

    if all_available:
        response.append("The items you ordered are available in our menu.")

    if invalid_toppings:
        response.append(
            f"Toppings not available: {', '.join(invalid_toppings)}. But we do have these available: {', '.join(sorted(topping_map.values()))}."
        )
    elif valid_toppings:
        response.append(f"Toppings available: {', '.join(sorted(set(topping_map[t] for t in valid_toppings)))}.")

    return "\n".join(response)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
