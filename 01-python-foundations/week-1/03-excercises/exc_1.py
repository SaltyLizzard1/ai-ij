# Exercise 1: Python Environment and Basic Data Types
# Purpose: Verify setup and practice basic Python operations

def test_numeric_operations():
    """
    Practice basic numeric operations and print results
    """
    x = 10
    y = 5
    
    print("\nNumeric Operations:")
    print(f"Addition: {x} + {y} = {x + y}")
    print(f"Subtraction: {x} - {y} = {x - y}")
    print(f"Multiplication: {x} * {y} = {x * y}")
    print(f"Division: {x} / {y} = {x / y}")
    
    # Return values for potential testing
    return {
        "addition": x + y,
        "subtraction": x - y,
        "multiplication": x * y,
        "division": x / y
    }

if __name__ == "__main__":
    print("Running Python Environment Test")
    results = test_numeric_operations()
    print("\nExercise completed successfully!")