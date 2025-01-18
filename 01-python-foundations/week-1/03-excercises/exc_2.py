# Exercise 2: Data Structure Operations
# Purpose: Practice working with lists, dictionaries, and basic data manipulation

def analyze_sales_data():
    """
    Simulate analyzing sales data using different Python data structures
    """
    # Sample sales data
    sales = [
        {"product": "laptop", "price": 999.99, "quantity": 3},
        {"product": "mouse", "price": 24.99, "quantity": 10},
        {"product": "keyboard", "price": 49.99, "quantity": 5},
        {"product": "monitor", "price": 199.99, "quantity": 2}
    ]

    # Calculate total sales and find most popular item
    total_sales = 0
    max_quantity = 0
    popular_item = ""

    # Process the sales data
    for item in sales:
        item_total = item["price"] * item["quantity"]
        total_sales += item_total
        
        if item["quantity"] > max_quantity:
            max_quantity = item["quantity"]
            popular_item = item["product"]

    # Create a summary dictionary
    summary = {
        "total_sales": round(total_sales, 2),
        "most_popular": popular_item,
        "num_products": len(sales)
    }

    return summary

# Add this main block at the end
if __name__ == "__main__":
    results = analyze_sales_data()
    print("\nSales Analysis:")
    for key, value in results.items():
        print(f"{key.replace('_', ' ').title()}: {value}")